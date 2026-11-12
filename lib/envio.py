"""
Envío de email por SNS.

Los eventos no traen correos (ARQ-01: payload mínimo), así que el email sale por el
topic nubeduca-${stage}-notificaciones con atributos tenantId, userId y type. Cada
correo se suscribe al topic con una política de filtro por userId
(scripts/suscribir_email.sh), y SNS se lo entrega solo a esa persona.
"""

import boto3

from lib import config, logs

_cliente = None


def _sns():
    global _cliente
    if _cliente is None:
        _cliente = boto3.client("sns")
    return _cliente


def reiniciar() -> None:
    global _cliente
    _cliente = None


def enviar(tenant_id: str, user_id: str, tipo: str, titulo: str, cuerpo: str) -> bool:
    """Publica el email. Devuelve False si no se pudo (el aviso queda FAILED)."""
    topic = config.topic_email()
    if not topic:
        logs.error(mensaje="Falta TOPIC_EMAIL; no se envía el email", userId=user_id, tipo=tipo)
        return False
    try:
        _sns().publish(
            TopicArn=topic,
            Subject=f"Nubeduca · {titulo}"[:100],
            Message=cuerpo,
            MessageAttributes={
                "tenantId": {"DataType": "String", "StringValue": tenant_id},
                "userId": {"DataType": "String", "StringValue": user_id},
                "type": {"DataType": "String", "StringValue": tipo},
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de SNS deja el aviso en FAILED
        logs.error(mensaje="No se pudo publicar el email", userId=user_id, tipo=tipo, error=str(exc))
        return False
