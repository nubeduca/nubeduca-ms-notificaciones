"""GET /health (pública)."""

from lib.http import respuesta


def lambda_handler(event, context):
    return respuesta(200, {"status": "ok", "service": "ms-notificaciones", "version": "1.0.0"})
