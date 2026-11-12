"""Acceso a la tabla única ${stage}-t_notificaciones (PK tenant_id, SK sk)."""

import boto3

from lib import config

_recurso = None


def tabla():
    global _recurso
    if _recurso is None:
        _recurso = boto3.resource("dynamodb")
    return _recurso.Table(config.tabla_nombre())


def reiniciar() -> None:
    """Solo para pruebas: fuerza a crear el cliente de nuevo."""
    global _recurso
    _recurso = None


# Claves de ordenamiento (sk) de cada tipo de ítem.
def sk_prefs(user_id: str) -> str:
    return f"USER#{user_id}#PREFS"


def sk_aviso_prefijo(user_id: str) -> str:
    return f"USER#{user_id}#NTF#"


def sk_aviso(user_id: str, created_at: str, ntf_id: str) -> str:
    return f"{sk_aviso_prefijo(user_id)}{created_at}#{ntf_id}"


def sk_curso_info(course_id: str) -> str:
    return f"COURSE#{course_id}#INFO"


def sk_miembro_prefijo(course_id: str) -> str:
    return f"COURSE#{course_id}#MEMBER#"


def sk_miembro(course_id: str, user_id: str) -> str:
    return f"{sk_miembro_prefijo(course_id)}{user_id}"


def sk_agregado(tipo: str, agregado_id: str) -> str:
    return f"AGG#{tipo}#{agregado_id}"


def sk_inbox(event_id: str) -> str:
    return f"INBOX#{event_id}"
