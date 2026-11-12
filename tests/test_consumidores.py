import json

import boto3
from boto3.dynamodb.conditions import Key

from consumidores import eventos_bus, notas_fifo
from lib import tabla as t
from tests.conftest import ALUMNO, ALUMNO_2, CURSO, DOCENTE, TENANT, evento, sqs_evento


def bandeja(user_id):
    return t.tabla().query(
        KeyConditionExpression=Key("tenant_id").eq(TENANT)
        & Key("sk").begins_with(t.sk_aviso_prefijo(user_id))
    )["Items"]


def matricular(*alumnos):
    for alumno in alumnos:
        eventos_bus.lambda_handler(
            sqs_evento(
                evento(
                    "lms.courses.enrollment.created.v1",
                    {"enrollmentId": f"enr_{alumno[:4]}", "userId": alumno, "role": "STUDENT"},
                    agregado=f"enr_{alumno[:4]}",
                )
            ),
            None,
        )
    eventos_bus.lambda_handler(
        sqs_evento(
            evento(
                "lms.courses.enrollment.created.v1",
                {"enrollmentId": "enr_doc", "userId": DOCENTE, "role": "TEACHER"},
                agregado="enr_doc",
            )
        ),
        None,
    )


def test_user_provisioned_crea_preferencias_por_defecto_sin_pisar():
    from lib import preferencias

    preferencias.guardar(TENANT, ALUMNO, {"email": {k: False for k in preferencias.CLAVES}}, "x")
    eventos_bus.lambda_handler(
        sqs_evento(
            evento("lms.users.user.provisioned.v1", {"userId": ALUMNO, "role": "STUDENT"}, tipo="user", curso=None),
            evento("lms.users.user.provisioned.v1", {"userId": ALUMNO_2, "role": "STUDENT"}, tipo="user", curso=None),
        ),
        None,
    )
    assert preferencias.leer(TENANT, ALUMNO)["email"]["grades"] is False  # respetó las suyas
    assert all(preferencias.leer(TENANT, ALUMNO_2)["email"].values())


def test_curso_publicado_avisa_solo_a_alumnos_y_manda_email(correos):
    matricular(ALUMNO, ALUMNO_2)
    respuesta = eventos_bus.lambda_handler(
        sqs_evento(evento("lms.courses.course.published.v1", {"title": "Cloud Computing"}, tipo="course", agregado=CURSO)),
        None,
    )
    assert respuesta == {"batchItemFailures": []}
    assert [a["title"] for a in bandeja(ALUMNO)] == ["Se publicó el curso Cloud Computing"]
    assert len(bandeja(ALUMNO_2)) == 1
    assert bandeja(DOCENTE) == []
    enviados = correos()
    assert len(enviados) == 2
    assert {m["MessageAttributes"]["userId"]["Value"] for m in enviados} == {ALUMNO, ALUMNO_2}
    assert all(a["status"] == "SENT" for a in bandeja(ALUMNO) + bandeja(ALUMNO_2))


def test_preferencia_desactivada_no_envia_email(correos):
    from lib import preferencias

    matricular(ALUMNO)
    prefs = preferencias.por_defecto()
    prefs["email"]["modules"] = False
    preferencias.guardar(TENANT, ALUMNO, prefs, "x")
    eventos_bus.lambda_handler(
        sqs_evento(
            evento("lms.content.module.published.v1", {"moduleId": "mod_1", "title": "Semana 1", "position": 1, "itemCount": 3}, tipo="module")
        ),
        None,
    )
    [aviso] = bandeja(ALUMNO)
    assert aviso["status"] == "SKIPPED_BY_PREFERENCE"
    assert correos() == []


def test_evento_duplicado_no_duplica_aviso_ni_email(correos):
    matricular(ALUMNO)
    e = evento(
        "lms.assessment.submission.submitted.v1",
        {"submissionId": "sbm_1", "assignmentId": "asg_1", "studentId": ALUMNO, "attempt": 2, "fileIds": ["fil_1"], "late": True},
        tipo="submission",
    )
    eventos_bus.lambda_handler(sqs_evento(e), None)
    eventos_bus.lambda_handler(sqs_evento(e), None)  # SQS lo entrega otra vez
    avisos = bandeja(ALUMNO)
    assert len(avisos) == 1
    assert avisos[0]["type"] == "SUBMISSION_RECEIPT"
    [correo] = correos()
    assert "Intento 2 (tardía)" in correo["Message"]


def test_reintento_tras_caida_completa_sin_reenviar(correos, monkeypatch):
    """Si el Lambda se cae después de crear los avisos, el reintento no reenvía correos."""
    from lib import eventos

    matricular(ALUMNO, ALUMNO_2)
    e = evento("lms.assessment.assignment.published.v1", {"assignmentId": "asg_9", "title": "Lab 9", "dueAt": "2026-11-20T23:59:00Z", "maxScore": 20}, tipo="assignment")
    original = eventos._confirmar
    monkeypatch.setattr(eventos, "_confirmar", lambda *a: (_ for _ in ()).throw(RuntimeError("caída")))
    assert eventos_bus.lambda_handler(sqs_evento(e), None)["batchItemFailures"] == [{"itemIdentifier": "m0"}]
    monkeypatch.setattr(eventos, "_confirmar", original)
    assert eventos_bus.lambda_handler(sqs_evento(e), None)["batchItemFailures"] == []
    assert len(bandeja(ALUMNO)) == 1 and len(bandeja(ALUMNO_2)) == 1
    assert len(correos()) == 2


def test_evento_viejo_se_descarta():
    matricular(ALUMNO)
    retiro = evento("lms.courses.enrollment.dropped.v1", {"enrollmentId": "enr_x", "userId": ALUMNO}, agregado="enr_x", version=3)
    alta_vieja = evento("lms.courses.enrollment.created.v1", {"enrollmentId": "enr_x", "userId": ALUMNO, "role": "STUDENT"}, agregado="enr_x", version=2)
    eventos_bus.lambda_handler(sqs_evento(retiro), None)
    eventos_bus.lambda_handler(sqs_evento(alta_vieja), None)  # llegó tarde
    miembro = t.tabla().get_item(Key={"tenant_id": TENANT, "sk": t.sk_miembro(CURSO, ALUMNO)}).get("Item")
    assert miembro is None


def test_nota_publicada_por_cola_fifo(correos):
    eventos_bus.lambda_handler(
        sqs_evento(evento("lms.courses.course.published.v1", {"title": "Cloud Computing"}, tipo="course", agregado=CURSO)), None
    )
    e = evento(
        "lms.grading.grade.posted.v1",
        {"gradeId": "grd_1", "gradeItemId": "gri_1", "studentId": ALUMNO, "score": 17, "maxScore": 20},
        tipo="grade",
    )
    # Raw delivery desde SNS FIFO: solo el detail, sin detail-type.
    respuesta = notas_fifo.lambda_handler({"Records": [{"messageId": "f1", "body": json.dumps(e["detail"])}]}, None)
    assert respuesta == {"batchItemFailures": []}
    [aviso] = bandeja(ALUMNO)
    assert aviso["type"] == "GRADE" and aviso["title"] == "Nota publicada en Cloud Computing"
    [correo] = correos()
    assert "17/20" in correo["Message"]


def test_grade_posted_por_el_bus_se_ignora():
    e = evento("lms.grading.grade.posted.v1", {"gradeId": "g", "gradeItemId": "gi", "studentId": ALUMNO, "score": 1, "maxScore": 20}, tipo="grade")
    eventos_bus.lambda_handler(sqs_evento(e), None)
    assert bandeja(ALUMNO) == []


def test_mensaje_roto_va_a_reintento_sin_tumbar_el_lote():
    matricular(ALUMNO)
    bueno = evento("lms.courses.announcement.published.v1", {"announcementId": "ann_1", "authorId": DOCENTE, "title": "Clase suspendida"}, tipo="announcement")
    lote = sqs_evento(bueno)
    lote["Records"].append({"messageId": "roto", "body": "{no es json"})
    respuesta = eventos_bus.lambda_handler(lote, None)
    assert respuesta == {"batchItemFailures": [{"itemIdentifier": "roto"}]}
    assert len(bandeja(ALUMNO)) == 1


def test_sin_topic_el_aviso_queda_failed(monkeypatch):
    from lib import envio

    monkeypatch.setenv("TOPIC_EMAIL", "")
    envio.reiniciar()
    matricular(ALUMNO)
    eventos_bus.lambda_handler(
        sqs_evento(evento("lms.courses.course.published.v1", {"title": "X"}, tipo="course", agregado=CURSO)), None
    )
    assert bandeja(ALUMNO)[0]["status"] == "FAILED"
