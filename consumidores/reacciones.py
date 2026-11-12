"""Qué hace ms-notificaciones con cada evento del catálogo (eventos/catalogo.yaml)."""

import os
from datetime import datetime

from boto3.dynamodb.conditions import Key

from lib import preferencias
from lib import tabla as t
from lib.eventos import Efectos, Evento, ahora_iso


def _curso(evento: Evento) -> str:
    """Nombre del curso guardado cuando se publicó; si no se conoce, un texto genérico."""
    if not evento.course_id:
        return "tu curso"
    item = t.tabla().get_item(
        Key={"tenant_id": evento.tenant_id, "sk": t.sk_curso_info(evento.course_id)}
    ).get("Item")
    return (item or {}).get("title") or "tu curso"


def _alumnos(evento: Evento) -> list[str]:
    if not evento.course_id:
        return []
    alumnos, inicio = [], None
    while True:
        consulta = {
            "KeyConditionExpression": Key("tenant_id").eq(evento.tenant_id)
            & Key("sk").begins_with(t.sk_miembro_prefijo(evento.course_id)),
        }
        if inicio:
            consulta["ExclusiveStartKey"] = inicio
        pagina = t.tabla().query(**consulta)
        alumnos += [i["userId"] for i in pagina["Items"] if i.get("role") == "STUDENT"]
        inicio = pagina.get("LastEvaluatedKey")
        if not inicio:
            return alumnos


def _cuerpo(titulo: str, detalle: str = "") -> str:
    url = os.environ.get("FRONTEND_URL", "")
    partes = [titulo]
    if detalle:
        partes.append(detalle)
    if url:
        partes.append(f"Entra a Nubeduca: {url}")
    partes.append("Puedes desactivar estos correos en Notificaciones → Preferencias.")
    return "\n\n".join(partes)


def _fecha(valor: str) -> str:
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except ValueError:
        return valor


def _aviso_a_alumnos(evento: Evento, tipo: str, titulo: str, detalle: str = "") -> Efectos:
    cuerpo = _cuerpo(titulo, detalle)
    return Efectos(
        avisos=[
            {"user_id": alumno, "tipo": tipo, "titulo": titulo, "cuerpo": cuerpo}
            for alumno in _alumnos(evento)
        ]
    )


# --- Reacciones -----------------------------------------------------------------


def user_provisioned(evento: Evento) -> Efectos:
    """Primer login: preferencias por defecto (sin pisar las que ya existan)."""
    user_id = evento.data["userId"]
    return Efectos(
        escrituras=[
            {
                "Update": {
                    "Key": {"tenant_id": evento.tenant_id, "sk": t.sk_prefs(user_id)},
                    "UpdateExpression": (
                        "SET #p = if_not_exists(#p, :p), entidad = :e, userId = :u, "
                        "updatedAt = if_not_exists(updatedAt, :t)"
                    ),
                    "ExpressionAttributeNames": {"#p": "preferences"},
                    "ExpressionAttributeValues": {
                        ":p": preferencias.por_defecto(),
                        ":e": "PREFERENCIAS",
                        ":u": user_id,
                        ":t": ahora_iso(),
                    },
                }
            }
        ]
    )


def _usuario_matricula(evento: Evento) -> str:
    # El contrato usa userId; el ejemplo de LOC-01 trae studentId. Lector tolerante: ambos.
    return evento.data.get("userId") or evento.data["studentId"]


def enrollment_created(evento: Evento) -> Efectos:
    user_id = _usuario_matricula(evento)
    return Efectos(
        escrituras=[
            {
                "Put": {
                    "Item": {
                        "tenant_id": evento.tenant_id,
                        "sk": t.sk_miembro(evento.course_id, user_id),
                        "entidad": "MATRICULADO",
                        "courseId": evento.course_id,
                        "userId": user_id,
                        "role": evento.data.get("role", "STUDENT"),
                        "enrollmentId": evento.data.get("enrollmentId"),
                    }
                }
            }
        ]
    )


def enrollment_dropped(evento: Evento) -> Efectos:
    return Efectos(
        escrituras=[
            {
                "Delete": {
                    "Key": {
                        "tenant_id": evento.tenant_id,
                        "sk": t.sk_miembro(evento.course_id, _usuario_matricula(evento)),
                    }
                }
            }
        ]
    )


def course_published(evento: Evento) -> Efectos:
    nombre = evento.data.get("title") or "tu curso"
    efectos = _aviso_a_alumnos(
        evento,
        "COURSE_PUBLISHED",
        f"Se publicó el curso {nombre}",
        "Ya puedes ver sus contenidos y tareas.",
    )
    efectos.escrituras.append(
        {
            "Put": {
                "Item": {
                    "tenant_id": evento.tenant_id,
                    "sk": t.sk_curso_info(evento.course_id),
                    "entidad": "CURSO",
                    "courseId": evento.course_id,
                    "title": nombre,
                }
            }
        }
    )
    return efectos


def module_published(evento: Evento) -> Efectos:
    return _aviso_a_alumnos(
        evento, "MODULE", f"Nuevo módulo en {_curso(evento)}: {evento.data.get('title', '')}"
    )


def announcement_published(evento: Evento) -> Efectos:
    return _aviso_a_alumnos(
        evento, "ANNOUNCEMENT", f"Aviso en {_curso(evento)}: {evento.data.get('title', '')}"
    )


def assignment_published(evento: Evento) -> Efectos:
    detalle = ""
    if evento.data.get("dueAt"):
        detalle = f"Fecha límite: {_fecha(evento.data['dueAt'])}."
    return _aviso_a_alumnos(
        evento,
        "ASSIGNMENT",
        f"Nueva tarea en {_curso(evento)}: {evento.data.get('title', '')}",
        detalle,
    )


def submission_submitted(evento: Evento) -> Efectos:
    intento = evento.data.get("attempt", 1)
    tardia = " (tardía)" if evento.data.get("late") else ""
    titulo = f"Recibimos tu entrega en {_curso(evento)}"
    detalle = f"Intento {intento}{tardia}. Guarda este correo como constancia."
    return Efectos(
        avisos=[
            {
                "user_id": evento.data["studentId"],
                "tipo": "SUBMISSION_RECEIPT",
                "titulo": titulo,
                "cuerpo": _cuerpo(titulo, detalle),
            }
        ]
    )


def grade_posted(evento: Evento) -> Efectos:
    score, max_score = evento.data.get("score"), evento.data.get("maxScore")
    titulo = f"Nota publicada en {_curso(evento)}"
    detalle = f"Tu nota: {score}/{max_score}." if score is not None else ""
    return Efectos(
        avisos=[
            {
                "user_id": evento.data["studentId"],
                "tipo": "GRADE",
                "titulo": titulo,
                "cuerpo": _cuerpo(titulo, detalle),
            }
        ]
    )


# Eventos que llegan por la regla del bus lms.
REACCIONES_BUS = {
    "lms.users.user.provisioned.v1": user_provisioned,
    "lms.courses.enrollment.created.v1": enrollment_created,
    "lms.courses.enrollment.dropped.v1": enrollment_dropped,
    "lms.courses.course.published.v1": course_published,
    "lms.content.module.published.v1": module_published,
    "lms.courses.announcement.published.v1": announcement_published,
    "lms.assessment.assignment.published.v1": assignment_published,
    "lms.assessment.submission.submitted.v1": submission_submitted,
}

# grade.posted llega SOLO por la cola FIFO (ARQ-01), para no mandar dos avisos.
REACCIONES_FIFO = {
    "lms.grading.grade.posted.v1": grade_posted,
}
