"""Lambda: cola FIFO nubeduca-${stage}-notificaciones-notas.fifo (tópico nubeduca-${stage}-notas.fifo de PLT-04)."""

from consumidores.reacciones import REACCIONES_FIFO
from lib.eventos import leer_mensaje, manejar_lote


def lambda_handler(event, context):
    # Raw delivery desde SNS FIFO: el body puede venir sin detail-type; es siempre grade.posted.
    for record in event.get("Records", []):
        try:
            if not leer_mensaje(record["body"]).detail_type:
                record["body"] = _con_tipo(record["body"])
        except Exception:  # noqa: BLE001 - manejar_lote lo reporta como fallido
            pass
    return manejar_lote(event, REACCIONES_FIFO)


def _con_tipo(cuerpo: str) -> str:
    import json

    mensaje = json.loads(cuerpo)
    mensaje.setdefault("detailType", "lms.grading.grade.posted.v1")
    return json.dumps(mensaje)
