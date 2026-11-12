"""Ids con prefijo + ULID (Crockford base32), como pide ARQ-01."""

import hashlib
import os
import time

ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _base32(valor: int, largo: int) -> str:
    salida = []
    for _ in range(largo):
        salida.append(ALFABETO[valor % 32])
        valor //= 32
    return "".join(reversed(salida))


def ulid(ms: int | None = None) -> str:
    ms = int(time.time() * 1000) if ms is None else ms
    return _base32(ms, 10) + _base32(int.from_bytes(os.urandom(10), "big"), 16)


def ntf_determinista(event_id: str, user_id: str) -> str:
    """
    Id de aviso que siempre sale igual para el mismo (evento, usuario).
    Así, si SQS reintenta el mensaje, el aviso no se duplica ni se reenvía el email.
    Conserva el tiempo del eventId (sus primeros 10 caracteres) para que ordene bien.
    """
    resumen = hashlib.sha256(f"{event_id}:{user_id}".encode()).digest()
    return "ntf_" + event_id[:10].upper() + _base32(int.from_bytes(resumen[:10], "big"), 16)
