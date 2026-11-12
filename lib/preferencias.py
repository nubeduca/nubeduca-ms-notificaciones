"""Preferencias de email por usuario (esquema Preferences del contrato)."""

from lib import tabla as t

CLAVES = (
    "coursePublished",
    "announcements",
    "modules",
    "assignments",
    "submissionReceipts",
    "grades",
)

# Tipo de aviso → preferencia que lo controla.
PREFERENCIA_POR_TIPO = {
    "COURSE_PUBLISHED": "coursePublished",
    "ANNOUNCEMENT": "announcements",
    "MODULE": "modules",
    "ASSIGNMENT": "assignments",
    "SUBMISSION_RECEIPT": "submissionReceipts",
    "GRADE": "grades",
}


def por_defecto() -> dict:
    return {"email": {clave: True for clave in CLAVES}}


def leer(tenant_id: str, user_id: str) -> dict:
    """Si el usuario todavía no tiene preferencias, valen las de por defecto (todo activo)."""
    item = t.tabla().get_item(Key={"tenant_id": tenant_id, "sk": t.sk_prefs(user_id)}).get("Item")
    guardadas = (item or {}).get("preferences", {}).get("email", {})
    return {"email": {clave: bool(guardadas.get(clave, True)) for clave in CLAVES}}


def validar(cuerpo) -> dict | None:
    """Devuelve las preferencias normalizadas o None si el body no cumple el contrato."""
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("email"), dict):
        return None
    email = cuerpo["email"]
    if any(not isinstance(email.get(clave), bool) for clave in CLAVES):
        return None
    return {"email": {clave: email[clave] for clave in CLAVES}}


def guardar(tenant_id: str, user_id: str, preferencias: dict, ahora: str) -> None:
    t.tabla().put_item(
        Item={
            "tenant_id": tenant_id,
            "sk": t.sk_prefs(user_id),
            "entidad": "PREFERENCIAS",
            "userId": user_id,
            "preferences": preferencias,
            "updatedAt": ahora,
        }
    )


def activa(preferencias: dict, tipo: str) -> bool:
    return bool(preferencias["email"].get(PREFERENCIA_POR_TIPO[tipo], True))
