import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.modules.telegram.intenciones import Intencion, detectar
from app.services.telegram import ClienteTelegramHttp
from tests.doble_extractor import ExtractorFalso, actividad, usar_extractor
from tests.doble_redactor import RedactorFalso, usar_redactor
from tests.doble_telegram import (
    SECRETO_WEBHOOK,
    TelegramFalso,
    boton,
    enviar,
    mensaje,
    usar_telegram,
    vincular,
)
from tests.helpers import Sesion, categoria_id, crear_actividad
from tests.test_telegram import nuevo_id


@pytest.fixture(autouse=True)
def secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRETO_WEBHOOK)


@pytest.fixture
def telegram(client: TestClient) -> TelegramFalso:
    falso = TelegramFalso()
    usar_telegram(client, falso)
    return falso


def actividades(client: TestClient, sesion: Sesion) -> list[dict[str, Any]]:
    lista: list[dict[str, Any]] = client.get(
        "/api/v1/actividades", headers=sesion.headers
    ).json()
    return lista


def crear_con_fecha(client: TestClient, sesion: Sesion, titulo: str, dias: int) -> str:
    vence = (datetime.now(UTC) + timedelta(days=dias)).isoformat()
    respuesta = client.post(
        "/api/v1/actividades",
        json={
            "titulo": titulo,
            "categoria_id": categoria_id(client, sesion),
            "vence_en": vence,
        },
        headers=sesion.headers,
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


@pytest.mark.parametrize(
    ("texto", "intencion"),
    [
        ("Que me hace falta hacer?", Intencion.PENDIENTES),
        ("¿Qué me hace falta?", Intencion.PENDIENTES),
        ("oye dime que tengo mañana", Intencion.MANANA),
        ("¿Qué tengo hoy?", Intencion.HOY),
        ("esta semana", Intencion.SEMANA),
        ("cómo voy", Intencion.METAS),
        ("resumen por favor", Intencion.RESUMEN),
        ("hola", Intencion.SALUDO),
        ("Gracias!", Intencion.GRACIAS),
        ("sí", Intencion.CONFIRMAR),
        ("No", Intencion.CANCELAR),
        ("para el temporizador", Intencion.TIMER_DETENER),
        ("inicia el timer de estudio", Intencion.TIMER_INICIAR),
        ("ya terminé el reporte de redes", Intencion.COMPLETAR),
    ],
)
def test_detecta_intenciones(texto: str, intencion: Intencion) -> None:
    detectada = detectar(texto)
    assert detectada is not None and detectada.intencion is intencion


@pytest.mark.parametrize(
    "texto",
    [
        "entregar el reporte de redes el viernes a las 6",
        "me falta entregar el reporte",
        "recuérdame que tengo que hacer la tarea mañana",
        "estudié 2 horas de bases de datos",
    ],
)
def test_las_instrucciones_no_se_confunden_con_consultas(texto: str) -> None:
    detectada = detectar(texto)
    assert detectada is None or detectada.intencion is Intencion.COMPLETAR


async def test_el_cliente_http_reparte_los_botones_en_filas() -> None:
    cuerpos: list[dict[str, Any]] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(peticion.content))
        return httpx.Response(200, json={"ok": True})

    cliente = ClienteTelegramHttp("token", transport=httpx.MockTransport(responder))
    botones = [(f"B{n}", f"d:{n}") for n in range(7)]

    await cliente.enviar(1, "texto", botones)
    filas = cuerpos[0]["reply_markup"]["inline_keyboard"]
    assert [len(f) for f in filas] == [3, 3, 1]


def test_una_pregunta_de_pendientes_no_llama_al_modelo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    extractor = ExtractorFalso(actividad())
    usar_extractor(client, extractor)
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "Que me hace falta hacer?"))
    assert "No tienes nada pendiente" in telegram.textos(tid)[-1]
    crear_actividad(client, ana, "Entregar reporte de redes")
    enviar(client, mensaje(tid, "que me hace falta hacer?"))
    assert "Entregar reporte de redes" in telegram.textos(tid)[-1]
    assert extractor.llamadas == []


def test_pendientes_marca_vencidas_y_completa_con_el_boton(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    crear_con_fecha(client, ana, "Leer capítulo", 3)
    crear_actividad(client, ana, "Sin fecha")
    enviar(client, mensaje(tid, "/pendientes"))
    _, texto, botones = telegram.enviados[-1]
    assert "1. Leer capítulo" in texto and "2. Sin fecha — sin fecha" in texto
    assert botones is not None and [b[0] for b in botones] == ["Hecha 1", "Hecha 2"]
    enviar(client, boton(tid, botones[0][1]))
    assert "marqué «Leer capítulo» como completada" in telegram.textos(tid)[-1]
    estados = {a["titulo"]: a["estado"] for a in actividades(client, ana)}
    assert estados["Leer capítulo"] == "completada"
    assert estados["Sin fecha"] == "pendiente"
    enviar(client, boton(tid, botones[0][1]))
    assert "ya estaba completada" in telegram.textos(tid)[-1]


def test_la_agenda_por_dia_y_semana(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "/hoy"))
    assert "No tienes nada programado para hoy" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/mañana"))
    assert "para mañana" in telegram.textos(tid)[-1]
    crear_con_fecha(client, ana, "Examen de redes", 2)
    enviar(client, mensaje(tid, "qué tengo esta semana"))
    assert "Examen de redes" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/semana"))
    assert "Los próximos 7 días" in telegram.textos(tid)[-1]


def test_completar_por_texto_y_con_varias_coincidencias(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    crear_actividad(client, ana, "Reporte de redes")
    crear_actividad(client, ana, "Reporte de bases")
    crear_actividad(client, ana, "Leer el capítulo")
    enviar(client, mensaje(tid, "/completar reporte"))
    _, texto, botones = telegram.enviados[-1]
    assert "varias" in texto and botones is not None and len(botones) == 2
    enviar(client, mensaje(tid, "/completar reporte de redes"))
    assert "marqué «Reporte de redes»" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/completar nada que ver"))
    assert "No encontré" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/completar"))
    assert telegram.enviados[-1][2] is not None


def test_terminar_en_lenguaje_natural_completa_o_deja_pasar(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    extractor = ExtractorFalso(actividad("Algo", modalidad="presencial"))
    usar_extractor(client, extractor)
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    crear_actividad(client, ana, "Entregar reporte de redes")
    enviar(client, mensaje(tid, "ya terminé el reporte de redes"))
    assert "marqué «Entregar reporte de redes»" in telegram.textos(tid)[-1]
    assert extractor.llamadas == []
    enviar(client, mensaje(tid, "terminé de estudiar 2 horas"))
    assert len(extractor.llamadas) == 1


def test_si_falta_el_titulo_la_siguiente_respuesta_lo_completa(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    usar_extractor(client, ExtractorFalso(actividad("", categoria=None)))
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "tengo algo pendiente"))
    _, texto, botones = telegram.enviados[-1]
    assert "¿Cómo se llama?" in texto
    assert botones is not None and [b[0] for b in botones] == ["Descartar"]
    enviar(client, mensaje(tid, "Reporte de redes"))
    guardado = telegram.textos(tid)[-1]
    assert "Listo, guardé la actividad" in guardado and "Reporte de redes" in guardado
    assert [a["titulo"] for a in actividades(client, ana)] == ["Reporte de redes"]


def test_una_instruccion_larga_no_se_toma_como_titulo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    usar_extractor(client, ExtractorFalso(actividad("", categoria="Tarea")))
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "tengo algo pendiente"))
    extractor = ExtractorFalso(actividad("Entregar reporte", modalidad="presencial"))
    usar_extractor(client, extractor)
    enviar(client, mensaje(tid, "entregar el reporte de bases el viernes a las 6"))
    assert len(extractor.llamadas) == 1
    assert actividades(client, ana) == []


def test_la_categoria_se_elige_con_botones(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    usar_extractor(
        client, ExtractorFalso(actividad("Entregar", categoria=None, modalidad="mixta"))
    )
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "entregar algo"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    nombres = [b[0] for b in botones[:-1]]
    assert nombres == sorted(nombres, key=str.casefold) and "Estudio" in nombres
    elegido = botones[nombres.index("Estudio")][1]
    enviar(client, boton(tid, elegido))
    assert "• Categoría: Estudio" in telegram.textos(tid)[-1]
    creada = actividades(client, ana)
    assert [a["titulo"] for a in creada] == ["Entregar"]
    assert creada[0]["categoria_id"] == categoria_id(client, ana, "Estudio")


def test_un_boton_de_categoria_invalido_se_ignora(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    usar_extractor(
        client, ExtractorFalso(actividad("Entregar", categoria=None, modalidad="mixta"))
    )
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "entregar algo"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    captura = botones[0][1].split(":")[1]
    antes = len(telegram.enviados)
    enviar(client, boton(tid, f"k:{captura}:x"))
    assert len(telegram.enviados) == antes
    enviar(client, boton(tid, f"k:{captura}:99"))
    assert "ya no está disponible" in telegram.textos(tid)[-1]
    assert actividades(client, ana) == []


def test_si_y_no_confirman_o_descartan_el_borrador(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    usar_extractor(
        client, ExtractorFalso(actividad("Entregar reporte", modalidad="presencial"))
    )
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "no"))
    assert "No hay nada que cancelar" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "sí"))
    assert "No tengo nada pendiente por confirmar" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "entregar reporte"))
    enviar(client, mensaje(tid, "sí"))
    assert "Listo, guardé la actividad" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "entregar reporte"))
    enviar(client, mensaje(tid, "no"))
    assert "descarté el borrador" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "entregar reporte"))
    enviar(client, mensaje(tid, "/cancelar"))
    assert "descarté el borrador" in telegram.textos(tid)[-1]
    assert len(actividades(client, ana)) == 1


def test_si_con_la_modalidad_sin_responder_vuelve_a_preguntar(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "entregar reporte"))
    enviar(client, mensaje(tid, "sí"))
    assert "¿Qué modalidad tiene?" in telegram.textos(tid)[-1]
    assert actividades(client, ana) == []


def test_una_pregunta_desconocida_orienta_sin_llamar_al_modelo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    extractor = ExtractorFalso(actividad())
    usar_extractor(client, extractor)
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "¿Cuántos días tiene octubre?"))
    assert "/pendientes" in telegram.textos(tid)[-1]
    assert extractor.llamadas == []


def test_saludo_gracias_y_ayuda(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "hola"))
    assert "/ayuda" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "gracias"))
    assert "Aquí sigo" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "qué puedes hacer"))
    ayuda = telegram.textos(tid)[-1]
    assert all(c in ayuda for c in ("/pendientes", "/completar", "/resumen"))


def test_resumen_con_texto_y_sin_el(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_redactor(client, RedactorFalso(texto="Vas bien esta semana."))
    enviar(client, mensaje(tid, "/resumen"))
    assert telegram.textos(tid)[-1] == "Vas bien esta semana."
    crear_con_fecha(client, ana, "Examen de redes", 2)
    usar_redactor(client, RedactorFalso(falla="sin_modelo"))
    enviar(client, mensaje(tid, "dame un resumen"))
    texto = telegram.textos(tid)[-1]
    assert "estas son tus cifras" in texto and "Examen de redes" in texto


def test_materias_y_categorias(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "/materias"))
    assert "No tienes materias activas" in telegram.textos(tid)[-1]
    client.post(
        "/api/v1/materias",
        json={"nombre": "Redes", "periodo": "2026-3"},
        headers=ana.headers,
    )
    enviar(client, mensaje(tid, "/materias"))
    assert "• Redes" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/categorias"))
    assert "• Estudio" in telegram.textos(tid)[-1]


def test_el_temporizador_en_lenguaje_natural(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "inicia el timer de estudio"))
    assert "iniciado" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "para el temporizador"))
    assert "detenido" in telegram.textos(tid)[-1]


def test_las_consultas_solo_ven_datos_propios(
    client: TestClient, telegram: TelegramFalso, ana: Sesion, beto: Sesion
) -> None:
    tid_ana, tid_beto = nuevo_id(), nuevo_id()
    vincular(client, ana, telegram, tid_ana)
    vincular(client, beto, telegram, tid_beto)
    crear_con_fecha(client, ana, "Secreto de Ana", 2)
    for comando in ("/pendientes", "/semana", "/completar secreto"):
        enviar(client, mensaje(tid_beto, comando))
        assert "Secreto de Ana" not in telegram.textos(tid_beto)[-1]
