"""Lambda: cola nubeduca-${stage}-notificaciones-eventos (regla del bus lms)."""

from consumidores.reacciones import REACCIONES_BUS
from lib.eventos import manejar_lote


def lambda_handler(event, context):
    return manejar_lote(event, REACCIONES_BUS)
