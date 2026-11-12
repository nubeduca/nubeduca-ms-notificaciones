"""
Procesamiento de eventos de EventBridge con las reglas de consumo de ARQ-01:

- Lector tolerante: solo se leen los campos que se usan.
- Idempotencia: INBOX#<eventId> se escribe con attribute_not_exists en la misma
  TransactWriteItems que el cambio de estado.
- Orden: AGG#<tipo>#<id> guarda la última aggregateVersion; si llega una igual o
  menor, el evento es viejo y se descarta.
- Los avisos (y sus emails) se crean ANTES de confirmar el inbox, con ids
  deterministas: si el Lambda se cae a la mitad, el reintento completa lo que faltó
  sin duplicar nada.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from lib import logs
from lib import tabla as t

TTL_INBOX_SEGUNDOS = 7 * 24 * 60 * 60


@dataclass
class Evento:
    detail_type: str
    event_id: str
    tenant_id: str
    occurred_at: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    course_id: str | None
    data: dict


@dataclass
class Efectos:
    """Lo que produce una reacción: escrituras de estado y avisos a crear."""

    escrituras: list = field(default_factory=list)  # ítems para TransactWriteItems
    avisos: list = field(default_factory=list)  # kwargs para avisos.crear()


def ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer_mensaje(cuerpo: str) -> Evento:
    """
    Convierte el body de SQS en un Evento. Acepta el evento completo de EventBridge
    (regla del bus → SQS) o solo su `detail` (tópico SNS FIFO con raw delivery).
    """
    mensaje = json.loads(cuerpo)
    if "detail" in mensaje:
        detail_type = mensaje.get("detail-type", "")
        detail = mensaje["detail"]
    else:
        detail = mensaje
        detail_type = mensaje.get("detailType") or mensaje.get("detail-type") or ""
    if isinstance(detail, str):
        detail = json.loads(detail)

    meta = detail["metadata"]
    return Evento(
        detail_type=detail_type,
        event_id=meta["eventId"],
        tenant_id=meta["tenantId"],
        occurred_at=meta["occurredAt"],
        aggregate_type=meta["aggregateType"],
        aggregate_id=meta["aggregateId"],
        aggregate_version=int(meta["aggregateVersion"]),
        course_id=meta.get("courseId"),
        data=detail.get("data") or {},
    )


def _ya_procesado(evento: Evento) -> str | None:
    """Devuelve el motivo para descartar el evento, o None si hay que procesarlo."""
    tabla = t.tabla()
    if tabla.get_item(Key={"tenant_id": evento.tenant_id, "sk": t.sk_inbox(evento.event_id)}).get(
        "Item"
    ):
        return "DUPLICADO"
    agregado = tabla.get_item(
        Key={
            "tenant_id": evento.tenant_id,
            "sk": t.sk_agregado(evento.aggregate_type, evento.aggregate_id),
        }
    ).get("Item")
    if agregado and int(agregado["version"]) >= evento.aggregate_version:
        return "VIEJO"
    return None


def _confirmar(evento: Evento, escrituras: list) -> bool:
    """TransactWriteItems: inbox + versión + estado. False si otro proceso ganó la carrera."""
    nombre = t.tabla().name
    cliente = t.tabla().meta.client
    operaciones = [
        {
            "Put": {
                "TableName": nombre,
                "Item": {
                    "tenant_id": evento.tenant_id,
                    "sk": t.sk_inbox(evento.event_id),
                    "entidad": "INBOX",
                    "detailType": evento.detail_type,
                    "procesadoEn": ahora_iso(),
                    "ttl": int(time.time()) + TTL_INBOX_SEGUNDOS,
                },
                "ConditionExpression": "attribute_not_exists(sk)",
            }
        },
        {
            "Put": {
                "TableName": nombre,
                "Item": {
                    "tenant_id": evento.tenant_id,
                    "sk": t.sk_agregado(evento.aggregate_type, evento.aggregate_id),
                    "entidad": "AGREGADO",
                    "version": evento.aggregate_version,
                },
                "ConditionExpression": "attribute_not_exists(sk) OR version < :v",
                "ExpressionAttributeValues": {":v": evento.aggregate_version},
            }
        },
    ]
    for escritura in escrituras:
        (accion, cuerpo), = escritura.items()
        operaciones.append({accion: {"TableName": nombre, **cuerpo}})

    try:
        # meta.client del recurso ya serializa los tipos de Python ({'S': ...}).
        cliente.transact_write_items(TransactItems=operaciones)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            return False
        raise


def procesar(evento: Evento, reacciones: dict) -> str:
    """Aplica la reacción del detail-type. Devuelve qué pasó (para logs y pruebas)."""
    from lib import avisos

    reaccion = reacciones.get(evento.detail_type)
    if reaccion is None:
        logs.info(mensaje="Evento ignorado", detailType=evento.detail_type, eventId=evento.event_id)
        return "IGNORADO"

    motivo = _ya_procesado(evento)
    if motivo:
        logs.info(mensaje="Evento descartado", motivo=motivo, eventId=evento.event_id)
        return motivo

    efectos: Efectos = reaccion(evento)
    for aviso in efectos.avisos:
        avisos.crear(
            tenant_id=evento.tenant_id,
            event_id=evento.event_id,
            created_at=evento.occurred_at,
            course_id=evento.course_id,
            **aviso,
        )

    if not _confirmar(evento, efectos.escrituras):
        logs.info(mensaje="Evento descartado", motivo="CARRERA", eventId=evento.event_id)
        return "DUPLICADO"

    logs.info(
        mensaje="Evento procesado",
        detailType=evento.detail_type,
        eventId=evento.event_id,
        tenantId=evento.tenant_id,
        avisos=len(efectos.avisos),
    )
    return "PROCESADO"


def manejar_lote(event: dict, reacciones: dict) -> dict:
    """Handler de SQS con partial batch response: solo se reintentan los mensajes que fallan."""
    fallidos = []
    for record in event.get("Records", []):
        try:
            procesar(leer_mensaje(record["body"]), reacciones)
        except Exception as exc:  # noqa: BLE001 - el mensaje vuelve a la cola y luego a la DLQ
            logs.error(mensaje="Error procesando mensaje", messageId=record.get("messageId"), error=str(exc))
            fallidos.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": fallidos}
