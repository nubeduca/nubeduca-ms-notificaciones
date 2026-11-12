import base64
import json

from api import avisos, preferencias, salud
from lib import avisos as lib_avisos
from tests.conftest import ALUMNO, ALUMNO_2, TENANT


def peticion(token=None, method="GET", body=None, query=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return {
        "httpMethod": method,
        "headers": headers,
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
        "requestContext": {"requestId": "req-1"},
    }


TOKEN = f"mock.{TENANT}.STUDENT.{ALUMNO}"


def cuerpo(respuesta):
    return json.loads(respuesta["body"])


def test_health_publico():
    r = salud.lambda_handler({}, None)
    assert r["statusCode"] == 200 and cuerpo(r)["status"] == "ok"


def test_sin_token_401_con_formato_de_error():
    r = avisos.lambda_handler(peticion(), None)
    assert r["statusCode"] == 401
    assert cuerpo(r) == {"code": "NO_AUTENTICADO", "message": "Falta el token o no es válido.", "requestId": "req-1"}
    assert preferencias.lambda_handler(peticion("mock.otro.STUDENT.x"), None)["statusCode"] == 401


def test_preferencias_por_defecto_y_guardar():
    r = preferencias.lambda_handler(peticion(TOKEN), None)
    assert r["statusCode"] == 200 and all(cuerpo(r)["email"].values())

    nuevas = {"email": {"coursePublished": True, "announcements": False, "modules": True, "assignments": True, "submissionReceipts": False, "grades": True}}
    r = preferencias.lambda_handler(peticion(TOKEN, "PUT", nuevas), None)
    assert r["statusCode"] == 200 and cuerpo(r) == nuevas
    assert cuerpo(preferencias.lambda_handler(peticion(TOKEN), None)) == nuevas


def test_preferencias_invalidas_400():
    r = preferencias.lambda_handler(peticion(TOKEN, "PUT", {"email": {"grades": "si"}}), None)
    assert r["statusCode"] == 400 and cuerpo(r)["code"] == "DATOS_INVALIDOS"


def _sembrar(user_id, cantidad):
    for n in range(cantidad):
        lib_avisos.crear(
            tenant_id=TENANT,
            user_id=user_id,
            event_id=f"01JCMK0PDR72NVMBVR2W{n:06d}",
            created_at=f"2026-11-15T15:{n:02d}:00Z",
            tipo="MODULE",
            titulo=f"Aviso {n}",
            cuerpo="x",
            course_id="crs_01JCQRZHQT9F4WY2JYPDV546K7",
        )


def test_bandeja_paginada_mas_reciente_primero_y_aislada():
    _sembrar(ALUMNO, 5)
    _sembrar(ALUMNO_2, 2)
    r = avisos.lambda_handler(peticion(TOKEN, query={"limit": "3"}), None)
    pagina = cuerpo(r)
    assert [a["title"] for a in pagina["items"]] == ["Aviso 4", "Aviso 3", "Aviso 2"]
    assert pagina["nextToken"]
    assert set(pagina["items"][0]) == {"notificationId", "type", "title", "status", "createdAt", "courseId"}

    r2 = avisos.lambda_handler(peticion(TOKEN, query={"limit": "3", "nextToken": pagina["nextToken"]}), None)
    assert [a["title"] for a in cuerpo(r2)["items"]] == ["Aviso 1", "Aviso 0"]
    assert cuerpo(r2)["nextToken"] is None


def test_next_token_de_otro_usuario_se_rechaza():
    _sembrar(ALUMNO_2, 2)
    ajeno = base64.urlsafe_b64encode(json.dumps({"tenant_id": TENANT, "sk": f"USER#{ALUMNO_2}#NTF#z"}).encode()).decode()
    r = avisos.lambda_handler(peticion(TOKEN, query={"nextToken": ajeno}), None)
    assert r["statusCode"] == 400


def test_otro_tenant_no_ve_mis_avisos():
    _sembrar(ALUMNO, 2)
    r = avisos.lambda_handler(peticion(f"mock.upc.STUDENT.{ALUMNO}"), None)
    assert cuerpo(r)["items"] == []


def test_limit_fuera_de_rango_400():
    assert avisos.lambda_handler(peticion(TOKEN, query={"limit": "500"}), None)["statusCode"] == 400


def test_modo_cognito_lee_claims(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "cognito")
    evento = peticion()
    evento["requestContext"]["authorizer"] = {"claims": {"sub": ALUMNO, "custom:tenant_id": TENANT, "custom:role": "STUDENT"}}
    assert avisos.lambda_handler(evento, None)["statusCode"] == 200
    # En modo cognito un token mock no sirve.
    assert avisos.lambda_handler(peticion(TOKEN), None)["statusCode"] == 401
