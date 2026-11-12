"""Avisos de la bandeja (esquema Notification del contrato) y su email."""

from botocore.exceptions import ClientError

from lib import envio, logs, preferencias
from lib import tabla as t
from lib.ids import ntf_determinista


def a_contrato(item: dict) -> dict:
    """Ítem de DynamoDB → Notification del OpenAPI."""
    aviso = {
        "notificationId": item["notificationId"],
        "type": item["type"],
        "title": item["title"],
        # PENDING solo queda si el Lambda se cayó entre guardar y enviar: no salió el email.
        "status": "FAILED" if item["status"] == "PENDING" else item["status"],
        "createdAt": item["createdAt"],
    }
    if item.get("courseId"):
        aviso["courseId"] = item["courseId"]
    return aviso


def crear(
    *,
    tenant_id: str,
    user_id: str,
    event_id: str,
    created_at: str,
    tipo: str,
    titulo: str,
    cuerpo: str,
    course_id: str | None = None,
) -> str | None:
    """
    Guarda el aviso y manda el email si el usuario lo tiene activo.

    Es idempotente: el id sale del (eventId, userId) y la escritura es condicional,
    así que un reintento de SQS no duplica el aviso ni reenvía el correo.
    Devuelve el estado final, o None si el aviso ya existía.
    """
    ntf_id = ntf_determinista(event_id, user_id)
    clave = {"tenant_id": tenant_id, "sk": t.sk_aviso(user_id, created_at, ntf_id)}
    item = {
        **clave,
        "entidad": "AVISO",
        "notificationId": ntf_id,
        "userId": user_id,
        "type": tipo,
        "title": titulo,
        "status": "PENDING",
        "createdAt": created_at,
        "eventId": event_id,
    }
    if course_id:
        item["courseId"] = course_id

    try:
        t.tabla().put_item(Item=item, ConditionExpression="attribute_not_exists(sk)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        raise

    if not preferencias.activa(preferencias.leer(tenant_id, user_id), tipo):
        estado = "SKIPPED_BY_PREFERENCE"
    else:
        estado = "SENT" if envio.enviar(tenant_id, user_id, tipo, titulo, cuerpo) else "FAILED"

    t.tabla().update_item(
        Key=clave,
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": estado},
    )
    logs.info(mensaje="Aviso creado", tenantId=tenant_id, userId=user_id, tipo=tipo, estado=estado)
    return estado
