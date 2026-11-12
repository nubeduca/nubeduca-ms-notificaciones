"""Configuración del servicio leída de variables de entorno (serverless.yml)."""

import os

TENANTS = ("utec", "upc", "pucp")
ROLES = ("STUDENT", "TEACHER", "ADMIN")


def tabla_nombre() -> str:
    return os.environ.get("TABLA_NOTIFICACIONES", "dev-t_notificaciones")


def topic_email() -> str:
    return os.environ.get("TOPIC_EMAIL", "")


def auth_mode() -> str:
    """cognito: claims del authorizer de API Gateway · mock: token del frontend en modo demo."""
    return os.environ.get("AUTH_MODE", "cognito").lower()
