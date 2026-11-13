"""
Carga 30.000 registros ficticios en ${stage}-t_notificaciones: UTEC 15.000, UPC 10.000 y PUCP 5.000
(reparto acordado el 13 nov.).

Por tenant: 10 % preferencias de usuario (90 % alumnos, 10 % docentes) y 90 % avisos en las
bandejas de los alumnos. UTEC: 1.500 preferencias + 13.500 avisos.
No escribe ítems INBOX ni EVENTO#: cargar datos no dispara eventos ni correos.

Uso:
  python poblar_datos.py                       # stage dev en tu cuenta de AWS
  python poblar_datos.py --stage prod
  python poblar_datos.py --endpoint-url http://localhost:4566 --tabla local-t_notificaciones
"""

import argparse
import hashlib
import random
from datetime import datetime, timedelta, timezone

import boto3

REPARTO = {"utec": 15_000, "upc": 10_000, "pucp": 5_000}
TENANTS = tuple(REPARTO)
CURSOS_POR_TENANT = 1_000
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

TIPOS = [
    ("COURSE_PUBLISHED", "coursePublished", "Se publicó el curso {curso}"),
    ("ANNOUNCEMENT", "announcements", "Aviso en {curso}: cambio de horario"),
    ("MODULE", "modules", "Nuevo módulo en {curso}: Semana {n}"),
    ("ASSIGNMENT", "assignments", "Nueva tarea en {curso}: Laboratorio {n}"),
    ("SUBMISSION_RECEIPT", "submissionReceipts", "Recibimos tu entrega en {curso}"),
    ("GRADE", "grades", "Nota publicada en {curso}"),
]
CURSOS = [
    "Cloud Computing", "Arquitectura de Software", "Base de Datos Avanzada",
    "Sistemas Operativos", "Redes de Computadoras", "Ingeniería de Software",
    "Inteligencia Artificial", "Seguridad Informática", "Compiladores", "Análisis de Datos",
]


def base32(valor: int, largo: int) -> str:
    salida = []
    for _ in range(largo):
        salida.append(ALFABETO[valor % 32])
        valor //= 32
    return "".join(reversed(salida))


def ulid_fijo(semilla: str, momento: datetime) -> str:
    """ULID determinista: el mismo dato siempre genera el mismo id (cargar dos veces no duplica)."""
    ms = int(momento.timestamp() * 1000)
    resto = int.from_bytes(hashlib.sha256(semilla.encode()).digest()[:10], "big")
    return base32(ms, 10) + base32(resto, 16)


def uuid_usuario(tenant: str, n: int) -> str:
    """userId (sub de Cognito) ficticio y estable por tenant."""
    h = hashlib.sha256(f"{tenant}:usuario:{n}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def items_de_tenant(tenant: str):
    azar = random.Random(f"nubeduca-{tenant}")
    base = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    total = REPARTO[tenant]
    cantidad_usuarios = total // 10
    alumnos = cantidad_usuarios * 9 // 10  # el resto son docentes
    usuarios = [uuid_usuario(tenant, n) for n in range(1, cantidad_usuarios + 1)]
    preferencias_por_usuario = {}

    for user_id in usuarios:
        email = {clave: azar.random() > 0.15 for _, clave, _ in TIPOS}
        preferencias_por_usuario[user_id] = email
        yield {
            "tenant_id": tenant,
            "sk": f"USER#{user_id}#PREFS",
            "entidad": "PREFERENCIAS",
            "userId": user_id,
            "preferences": {"email": email},
            "updatedAt": base.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    for n in range(total - cantidad_usuarios):
        user_id = usuarios[n % alumnos]  # los avisos van a los alumnos
        tipo, clave, plantilla = TIPOS[n % len(TIPOS)]
        momento = base - timedelta(minutes=7 * n + azar.randint(0, 6))
        created_at = momento.strftime("%Y-%m-%dT%H:%M:%SZ")
        ntf_id = "ntf_" + ulid_fijo(f"{tenant}:aviso:{n}", momento)
        curso_n = azar.randint(1, CURSOS_POR_TENANT)
        course_id = "crs_" + ulid_fijo(f"{tenant}:curso:{curso_n}", base - timedelta(days=60))
        if not preferencias_por_usuario[user_id][clave]:
            estado = "SKIPPED_BY_PREFERENCE"
        else:
            estado = "FAILED" if azar.random() < 0.02 else "SENT"
        yield {
            "tenant_id": tenant,
            "sk": f"USER#{user_id}#NTF#{created_at}#{ntf_id}",
            "entidad": "AVISO",
            "notificationId": ntf_id,
            "userId": user_id,
            "type": tipo,
            "title": plantilla.format(curso=CURSOS[curso_n % len(CURSOS)], n=(n % 16) + 1),
            "courseId": course_id,
            "status": estado,
            "createdAt": created_at,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--tabla", help="Nombre de la tabla (por defecto <stage>-t_notificaciones)")
    parser.add_argument("--endpoint-url", help="Por ejemplo http://localhost:4566 para LocalStack")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    nombre = args.tabla or f"{args.stage}-t_notificaciones"
    dynamodb = boto3.resource("dynamodb", region_name=args.region, endpoint_url=args.endpoint_url)
    tabla = dynamodb.Table(nombre)

    total = 0
    for tenant in TENANTS:
        cantidad = 0
        with tabla.batch_writer(overwrite_by_pkeys=["tenant_id", "sk"]) as lote:
            for item in items_de_tenant(tenant):
                lote.put_item(Item=item)
                cantidad += 1
        total += cantidad
        print(f"{tenant}: {cantidad} registros")
    print(f"Total: {total} registros en {nombre}")


if __name__ == "__main__":
    main()
