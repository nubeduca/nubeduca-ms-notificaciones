"""Seed de ENG-01: 30.000 registros, UTEC 15.000, UPC 10.000 y PUCP 5.000 (decisión del 13 nov.)."""

from collections import Counter

import poblar_datos


def test_reparto_oficial():
    assert poblar_datos.REPARTO == {"utec": 15_000, "upc": 10_000, "pucp": 5_000}
    assert sum(poblar_datos.REPARTO.values()) == 30_000


def test_cada_tenant_recibe_su_cantidad():
    for tenant, total in poblar_datos.REPARTO.items():
        items = list(poblar_datos.items_de_tenant(tenant))
        assert len(items) == total
        assert len({i["sk"] for i in items}) == total  # sin claves repetidas
        assert {i["tenant_id"] for i in items} == {tenant}
        tipos = Counter(i["entidad"] for i in items)
        assert tipos["PREFERENCIAS"] == total // 10
        assert tipos["AVISO"] == total - total // 10


def test_los_avisos_van_a_alumnos_con_preferencias():
    items = list(poblar_datos.items_de_tenant("pucp"))
    con_preferencias = {i["userId"] for i in items if i["entidad"] == "PREFERENCIAS"}
    destinatarios = {i["userId"] for i in items if i["entidad"] == "AVISO"}
    assert destinatarios <= con_preferencias
    assert len(destinatarios) == len(con_preferencias) * 9 // 10  # 90 % alumnos, 10 % docentes


def test_es_determinista():
    assert list(poblar_datos.items_de_tenant("upc"))[:50] == list(poblar_datos.items_de_tenant("upc"))[:50]
