import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.services.formato import fecha_legible
from tests.doble_extractor import (
    ExtractorFalso,
    actividad,
    meta,
    registro,
    usar_extractor,
)
from tests.doble_telegram import (
    SECRETO_WEBHOOK,
    TelegramFalso,
    boton,
    enviar,
    generar_codigo,
    mensaje,
    usar_telegram,
    vincular,
)
from tests.helpers import Sesion
from tests.test_telegram import nuevo_id

UUID_EN_TEXTO = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-")
MEXICO = ZoneInfo("America/Mexico_City")
AHORA = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRETO_WEBHOOK)


@pytest.fixture
def telegram(client: TestClient) -> TelegramFalso:
    falso = TelegramFalso()
    usar_telegram(client, falso)
    return falso


def listar_actividades(client: TestClient, sesion: Sesion) -> list[dict[str, str]]:
    respuesta = client.get("/api/v1/actividades", headers=sesion.headers)
    lista: list[dict[str, str]] = respuesta.json()
    return lista


def test_el_resumen_usa_nombres_y_fechas_legibles(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    client.post(
        "/api/v1/materias",
        json={"nombre": "Redes", "periodo": "2026-3"},
        headers=ana.headers,
    )
    propuesta = actividad(
        "Entregar reporte",
        materia="Redes",
        fecha_texto="mañana",
        prioridad=4,
        modalidad="en_linea",
    )
    usar_extractor(client, ExtractorFalso(propuesta))
    enviar(client, mensaje(tid, "entregar reporte de redes mañana"))
    _, texto, botones = telegram.enviados[-1]
    assert "• Título: Entregar reporte" in texto
    assert re.search(r"• Vence: \w{3} \d{1,2} \w{3}(?: \d{4})?, 23:59", texto)
    assert "• Materia: Redes" in texto
    assert "• Categoría: Tarea" in texto
    assert "• Prioridad: 4 (alta)" in texto
    assert "• Modalidad: En línea" in texto
    assert not UUID_EN_TEXTO.search(texto)
    assert "T23:59" not in texto and "-06:00" not in texto
    assert botones is not None and [b[0] for b in botones] == ["Confirmar", "Descartar"]


def test_pregunta_la_modalidad_solo_si_el_mensaje_no_la_dice(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    enviar(client, mensaje(tid, "entregar reporte"))
    _, texto, botones = telegram.enviados[-1]
    assert "¿Qué modalidad tiene?" in texto
    assert "• Modalidad" not in texto
    assert botones is not None
    assert [b[0] for b in botones] == ["Presencial", "En línea", "Mixta", "Descartar"]
    assert listar_actividades(client, ana) == []


def test_elegir_la_modalidad_guarda_la_actividad_sin_contar_como_correccion(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    enviar(client, mensaje(tid, "entregar reporte"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    en_linea = botones[1][1]
    enviar(client, boton(tid, en_linea))
    enviar(client, boton(tid, en_linea))
    guardado = telegram.textos(tid)[-1]
    assert "Listo, guardé la actividad" in guardado
    assert "• Modalidad: En línea" in guardado
    actividades = listar_actividades(client, ana)
    assert [(a["titulo"], a["modalidad"]) for a in actividades] == [
        ("Entregar reporte", "en_linea")
    ]
    pipeline = client.get("/api/v1/capturas/metricas", headers=ana.headers).json()
    fila = next(f for f in pipeline if f["entidad_tipo"] == "actividad")
    assert (fila["aceptadas"], fila["corregidas"]) == (1, 0)


def test_la_modalidad_mixta_y_presencial_se_guardan(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Uno")))
    enviar(client, mensaje(tid, "uno"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    enviar(client, boton(tid, botones[2][1]))
    usar_extractor(client, ExtractorFalso(actividad("Dos")))
    enviar(client, mensaje(tid, "dos"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    enviar(client, boton(tid, botones[0][1]))
    guardadas = {a["titulo"]: a["modalidad"] for a in listar_actividades(client, ana)}
    assert guardadas == {"Uno": "mixta", "Dos": "presencial"}


def test_un_boton_de_modalidad_invalido_no_hace_nada(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    enviar(client, mensaje(tid, "entregar reporte"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    invalido = botones[0][1][:-1] + "z"
    antes = len(telegram.enviados)
    enviar(client, boton(tid, invalido))
    assert len(telegram.enviados) == antes
    assert listar_actividades(client, ana) == []


def test_un_boton_de_modalidad_ajeno_no_guarda_nada(
    client: TestClient, telegram: TelegramFalso, ana: Sesion, beto: Sesion
) -> None:
    tid_ana, tid_beto = nuevo_id(), nuevo_id()
    vincular(client, ana, telegram, tid_ana)
    vincular(client, beto, telegram, tid_beto)
    usar_extractor(client, ExtractorFalso(actividad("De Ana")))
    enviar(client, mensaje(tid_ana, "algo de ana"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    enviar(client, boton(tid_beto, botones[0][1]))
    assert "no existe" in telegram.textos(tid_beto)[-1]
    assert listar_actividades(client, ana) == []
    assert listar_actividades(client, beto) == []


def test_descartar_desde_la_pregunta_de_modalidad(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    enviar(client, mensaje(tid, "entregar reporte"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    enviar(client, boton(tid, botones[3][1]))
    assert "Descartado" in telegram.textos(tid)[-1]
    assert listar_actividades(client, ana) == []


def test_si_falta_un_dato_no_se_pregunta_la_modalidad(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar", categoria=None)))
    enviar(client, mensaje(tid, "entregar algo"))
    _, texto, botones = telegram.enviados[-1]
    assert "¿En qué categoría va?" in texto
    assert "¿Qué modalidad" not in texto
    assert botones is not None and botones[-1][0] == "Descartar"
    assert all(b[1].startswith("k:") for b in botones[:-1])


def test_registro_de_tiempo_y_meta_tambien_salen_legibles(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(registro("Estudio", 90)))
    enviar(client, mensaje(tid, "estudié 90 minutos"))
    _, texto, botones = telegram.enviados[-1]
    assert "• Categoría: Estudio" in texto and "• Inicio:" in texto
    assert not UUID_EN_TEXTO.search(texto)
    assert botones is not None and [b[0] for b in botones] == ["Confirmar", "Descartar"]
    usar_extractor(client, ExtractorFalso(meta("Ejercicio", 2)))
    enviar(client, mensaje(tid, "meta de 2 horas de ejercicio a la semana"))
    _, texto, botones = telegram.enviados[-1]
    assert "• Categoría: Ejercicio" in texto
    assert "• Tipo: Tiempo acumulado" in texto and "• Periodo: Semana" in texto
    assert not UUID_EN_TEXTO.search(texto)
    assert botones is not None and [b[0] for b in botones] == ["Confirmar", "Descartar"]


def test_start_con_codigo_vincula_la_cuenta(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    codigo = generar_codigo(client, ana)
    assert enviar(client, mensaje(tid, f"/start {codigo}")) == 200
    assert "Cuenta vinculada" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/ayuda"))
    assert "/tarea" in telegram.textos(tid)[-1]


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("2026-11-27T23:59:00-06:00", "vie 27 nov, 23:59"),
        ("2026-11-28T05:59:00+00:00", "vie 27 nov, 23:59"),
        ("2026-11-27T23:59:00", "vie 27 nov, 23:59"),
        ("2027-01-04T08:05:00-06:00", "lun 4 ene 2027, 08:05"),
        ("2026-12-02T09:00:00-06:00", "mié 2 dic, 09:00"),
        ("2026-12-05T18:30:00-06:00", "sáb 5 dic, 18:30"),
    ],
)
def test_fecha_legible(valor: str, esperado: str) -> None:
    assert fecha_legible(valor, MEXICO, AHORA) == esperado


def test_fecha_legible_deja_pasar_un_texto_que_no_es_fecha() -> None:
    assert fecha_legible("pronto", MEXICO, AHORA) == "pronto"
