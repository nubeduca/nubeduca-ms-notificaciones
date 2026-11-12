"""GET /notifications/me: avisos que recibí, el más reciente primero."""

import base64
import json

from boto3.dynamodb.conditions import Key

from lib import auth, avisos, http, logs
from lib import tabla as t


def _decodificar(token: str, tenant_id: str, prefijo: str):
    try:
        clave = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    # El token solo puede apuntar a la bandeja del propio usuario.
    if clave.get("tenant_id") != tenant_id or not str(clave.get("sk", "")).startswith(prefijo):
        return None
    return clave


def lambda_handler(event, context):
    try:
        usuario = auth.usuario(event)
        if not usuario:
            return http.no_autenticado(event)

        params = event.get("queryStringParameters") or {}
        try:
            limite = int(params.get("limit", 20))
        except ValueError:
            return http.datos_invalidos(event, "limit debe ser un número.")
        if not 1 <= limite <= 100:
            return http.datos_invalidos(event, "limit debe estar entre 1 y 100.")

        prefijo = t.sk_aviso_prefijo(usuario.user_id)
        consulta = {
            "KeyConditionExpression": Key("tenant_id").eq(usuario.tenant_id)
            & Key("sk").begins_with(prefijo),
            "ScanIndexForward": False,
            "Limit": limite,
        }
        if params.get("nextToken"):
            inicio = _decodificar(params["nextToken"], usuario.tenant_id, prefijo)
            if inicio is None:
                return http.datos_invalidos(event, "El token de paginación no es válido.")
            consulta["ExclusiveStartKey"] = inicio

        pagina = t.tabla().query(**consulta)
        siguiente = pagina.get("LastEvaluatedKey")
        return http.respuesta(
            200,
            {
                "items": [avisos.a_contrato(item) for item in pagina["Items"]],
                "nextToken": (
                    base64.urlsafe_b64encode(json.dumps(siguiente).encode()).decode()
                    if siguiente
                    else None
                ),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logs.error(mensaje="Error en /notifications/me", error=str(exc))
        return http.error(event, 500, "ERROR_INTERNO", "No se pudo completar la operación.")
