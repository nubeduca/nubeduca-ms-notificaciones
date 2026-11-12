"""GET y PUT /preferences/me."""

from lib import auth, http, logs, preferencias
from lib.eventos import ahora_iso


def lambda_handler(event, context):
    try:
        usuario = auth.usuario(event)
        if not usuario:
            return http.no_autenticado(event)

        if (event.get("httpMethod") or "GET").upper() == "PUT":
            nuevas = preferencias.validar(http.leer_json(event))
            if nuevas is None:
                return http.datos_invalidos(
                    event, "Envía email con los 6 valores booleanos de preferencias."
                )
            preferencias.guardar(usuario.tenant_id, usuario.user_id, nuevas, ahora_iso())
            logs.info(mensaje="Preferencias actualizadas", tenantId=usuario.tenant_id, userId=usuario.user_id)
            return http.respuesta(200, nuevas)

        return http.respuesta(200, preferencias.leer(usuario.tenant_id, usuario.user_id))
    except Exception as exc:  # noqa: BLE001
        logs.error(mensaje="Error en /preferences/me", error=str(exc))
        return http.error(event, 500, "ERROR_INTERNO", "No se pudo completar la operación.")
