import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.doble_extractor import ExtractorFalso, actividad, usar_extractor
from tests.doble_telegram import (
    CABECERA,
    SECRETO_WEBHOOK,
    TelegramFalso,
    boton,
    enviar,
    generar_codigo,
    mensaje,
    usar_telegram,
    vincular,
)
from tests.helpers import (
    Sesion,
    categoria_id,
    ejecutar_como_administrador,
)


@pytest.fixture(autouse=True)
def secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRETO_WEBHOOK)


@pytest.fixture
def telegram(client: TestClient) -> Iterator[TelegramFalso]:
    falso = TelegramFalso()
    usar_telegram(client, falso)
    yield falso


def nuevo_id() -> int:
    return random.randint(10**9, 10**10)


def test_webhook_sin_secreto_responde_401(
    client: TestClient, telegram: TelegramFalso
) -> None:
    tid = nuevo_id()
    assert enviar(client, mensaje(tid, "/ayuda"), cabeceras={}) == 401
    assert enviar(client, {"basura": True}, cabeceras={}) == 401
    assert telegram.enviados == []


def test_webhook_con_secreto_equivocado_responde_401(
    client: TestClient, telegram: TelegramFalso
) -> None:
    cabeceras = {"X-Telegram-Bot-Api-Secret-Token": "otro"}
    assert enviar(client, mensaje(nuevo_id(), "/ayuda"), cabeceras) == 401


def test_webhook_sin_secreto_configurado_rechaza_todo(
    client: TestClient, telegram: TelegramFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    assert enviar(client, mensaje(nuevo_id(), "/ayuda"), {}) == 401
    assert (
        enviar(
            client,
            mensaje(nuevo_id(), "/ayuda"),
            {"X-Telegram-Bot-Api-Secret-Token": ""},
        )
        == 401
    )


def test_actualizaciones_sin_mensaje_se_ignoran(
    client: TestClient, telegram: TelegramFalso
) -> None:
    assert enviar(client, {"update_id": 5, "edited_message": {"x": 1}}) == 200
    assert telegram.enviados == []


def test_vinculo_requiere_sesion(client: TestClient) -> None:
    assert client.post("/api/v1/telegram/vinculo").status_code == 401


def test_vincula_la_cuenta_con_un_codigo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    perfil = client.get("/api/v1/auth/yo", headers=ana.headers).json()
    assert perfil["telegram_id"] == tid


def test_un_codigo_solo_se_usa_una_vez(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    primero, segundo = nuevo_id(), nuevo_id()
    codigo = generar_codigo(client, ana)
    enviar(client, mensaje(primero, f"/vincular {codigo}"))
    enviar(client, mensaje(segundo, f"/vincular {codigo}"))
    assert "vinculada" in telegram.textos(primero)[-1]
    assert "no es válido" in telegram.textos(segundo)[-1]
    perfil = client.get("/api/v1/auth/yo", headers=ana.headers).json()
    assert perfil["telegram_id"] == primero


def test_un_codigo_expirado_no_vincula(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    codigo = generar_codigo(client, ana)
    ejecutar_como_administrador(
        "update vinculo_telegram set creado_en = now() - interval '20 minutes', "
        "expira_en = now() - interval '10 minutes' where usuario_id = %s",
        (ana.id,),
    )
    enviar(client, mensaje(tid, f"/vincular {codigo}"))
    assert "no es válido" in telegram.textos(tid)[-1]
    perfil = client.get("/api/v1/auth/yo", headers=ana.headers).json()
    assert perfil["telegram_id"] is None


def test_un_codigo_inventado_no_vincula(
    client: TestClient, telegram: TelegramFalso
) -> None:
    tid = nuevo_id()
    enviar(client, mensaje(tid, "/vincular ABCD2345"))
    assert "no es válido" in telegram.textos(tid)[-1]


def test_un_telegram_no_puede_estar_en_dos_cuentas(
    client: TestClient, telegram: TelegramFalso, ana: Sesion, beto: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    codigo = generar_codigo(client, beto)
    enviar(client, mensaje(tid, f"/vincular {codigo}"))
    assert "no es válido" in telegram.textos(tid)[-1]
    assert (
        client.get("/api/v1/auth/yo", headers=beto.headers).json()["telegram_id"]
        is None
    )


def test_un_telegram_sin_vincular_solo_recibe_instrucciones(
    client: TestClient, telegram: TelegramFalso
) -> None:
    extractor = ExtractorFalso(actividad())
    usar_extractor(client, extractor)
    tid = nuevo_id()
    for texto in ("entregar tarea mañana", "/tarea algo", "/timer", "/meta"):
        enviar(client, mensaje(tid, texto))
    assert all("vincular" in t for t in telegram.textos(tid))
    assert extractor.llamadas == []


def test_tarea_crea_una_actividad(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "/tarea Leer capítulo 4"))
    assert "Tarea creada" in telegram.textos(tid)[-1]
    titulos = [
        a["titulo"]
        for a in client.get("/api/v1/actividades", headers=ana.headers).json()
    ]
    assert titulos == ["Leer capítulo 4"]
    enviar(client, mensaje(tid, "/tarea"))
    assert "Uso:" in telegram.textos(tid)[-1]


def test_timer_inicia_y_detiene(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "/timer"))
    assert "iniciado" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/timer"))
    assert "en curso" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/timer ejercicio"))
    assert "Ya hay un temporizador" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/timer stop"))
    assert "detenido" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/timer stop"))
    assert "No hay un temporizador" in telegram.textos(tid)[-1]
    registros = client.get("/api/v1/registros-tiempo", headers=ana.headers).json()
    assert len(registros) == 1


def test_meta_lista_el_progreso(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "/meta"))
    assert "No tienes metas" in telegram.textos(tid)[-1]
    client.post(
        "/api/v1/metas",
        json={
            "categoria_id": categoria_id(client, ana, "Estudio"),
            "tipo": "tiempo_acumulado",
            "periodo": "semana",
            "objetivo": 300,
        },
        headers=ana.headers,
    )
    enviar(client, mensaje(tid, "/meta"))
    assert "Estudio (semana): 0/300 min (0%)" in telegram.textos(tid)[-1]


def test_texto_libre_crea_una_captura_con_botones_y_confirma(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    enviar(client, mensaje(tid, "entregar reporte de redes"))
    _, texto, botones = telegram.enviados[-1]
    assert "Entregar reporte" in texto
    assert botones is not None and [b[0] for b in botones] == ["Confirmar", "Descartar"]
    confirmar = botones[0][1]
    enviar(client, boton(tid, confirmar))
    enviar(client, boton(tid, confirmar))
    assert telegram.callbacks == ["cb-1", "cb-1"]
    actividades = client.get("/api/v1/actividades", headers=ana.headers).json()
    assert [a["titulo"] for a in actividades] == ["Entregar reporte"]


def test_descartar_desde_el_boton_no_crea_nada(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    enviar(client, mensaje(tid, "entregar reporte"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    descartar = botones[1][1]
    enviar(client, boton(tid, descartar))
    assert "Descartado" in telegram.textos(tid)[-1]
    assert client.get("/api/v1/actividades", headers=ana.headers).json() == []
    enviar(client, boton(tid, descartar.replace("d:", "c:")))
    assert "descartada" in telegram.textos(tid)[-1]


def test_un_boton_ajeno_no_confirma_la_captura_de_otro(
    client: TestClient, telegram: TelegramFalso, ana: Sesion, beto: Sesion
) -> None:
    tid_ana, tid_beto = nuevo_id(), nuevo_id()
    vincular(client, ana, telegram, tid_ana)
    vincular(client, beto, telegram, tid_beto)
    usar_extractor(client, ExtractorFalso(actividad("De Ana")))
    enviar(client, mensaje(tid_ana, "algo de ana"))
    botones = telegram.enviados[-1][2]
    assert botones is not None
    confirmar = botones[0][1]
    enviar(client, boton(tid_beto, confirmar))
    assert "no existe" in telegram.textos(tid_beto)[-1]
    assert client.get("/api/v1/actividades", headers=beto.headers).json() == []
    assert client.get("/api/v1/actividades", headers=ana.headers).json() == []


def test_si_el_modelo_falla_el_bot_avisa_y_no_guarda(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(None))
    assert enviar(client, mensaje(tid, "algo")) == 200
    assert "formulario manual" in telegram.textos(tid)[-1]


def test_comando_desconocido_y_ayuda(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "/nada"))
    assert "No conozco" in telegram.textos(tid)[-1]
    enviar(client, mensaje(tid, "/ayuda@kairo_bot"))
    assert "/tarea" in telegram.textos(tid)[-1]


def test_si_telegram_falla_al_responder_el_webhook_sigue_en_200(
    client: TestClient, telegram: TelegramFalso
) -> None:
    telegram.fallar = True
    assert enviar(client, mensaje(nuevo_id(), "/ayuda")) == 200


def test_mensaje_muy_largo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    enviar(client, mensaje(tid, "a" * 1500))
    assert "muy largo" in telegram.textos(tid)[-1]


def test_cabecera_correcta_es_la_unica_forma_de_entrar(
    client: TestClient, telegram: TelegramFalso
) -> None:
    assert enviar(client, mensaje(nuevo_id(), "/ayuda"), dict(CABECERA)) == 200


def test_el_codigo_se_acepta_en_minusculas_y_con_espacios(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    codigo = generar_codigo(client, ana)
    enviar(client, mensaje(tid, f"/vincular   {codigo.lower()}  "))
    assert "vinculada" in telegram.textos(tid)[-1]
