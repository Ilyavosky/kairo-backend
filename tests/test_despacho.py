import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.doble_telegram import (
    DESPACHAR,
    INTERNO,
    SECRETO_INTERNO,
    SECRETO_WEBHOOK,
    TelegramFalso,
    usar_telegram,
    vincular,
)
from tests.helpers import Sesion, crear_actividad

RECORDATORIOS = "/api/v1/recordatorios"


@pytest.fixture(autouse=True)
def secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNO_SECRET", SECRETO_INTERNO)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRETO_WEBHOOK)


@pytest.fixture
def telegram(client: TestClient) -> Iterator[TelegramFalso]:
    falso = TelegramFalso()
    usar_telegram(client, falso)
    yield falso


def nuevo_id() -> int:
    return random.randint(10**9, 10**10)


def programar(
    client: TestClient, sesion: Sesion, minutos: float = -5, titulo: str = "Reporte"
) -> str:
    momento = (datetime.now(UTC) + timedelta(minutes=minutos)).isoformat()
    respuesta = client.post(
        RECORDATORIOS,
        json={
            "actividad_id": crear_actividad(client, sesion, titulo),
            "momento": momento,
        },
        headers=sesion.headers,
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


def estado(client: TestClient, sesion: Sesion, id_: str) -> dict[str, object]:
    resultado: dict[str, object] = client.get(
        f"{RECORDATORIOS}/{id_}", headers=sesion.headers
    ).json()
    return resultado


def test_sin_credencial_interna_responde_401(client: TestClient) -> None:
    assert client.post(DESPACHAR).status_code == 401
    assert (
        client.post(DESPACHAR, headers={"Authorization": "Bearer otro"}).status_code
        == 401
    )


def test_un_jwt_de_usuario_no_sirve_para_el_despacho(
    client: TestClient, ana: Sesion
) -> None:
    assert client.post(DESPACHAR, headers=ana.headers).status_code == 401


def test_sin_secreto_configurado_se_rechaza_todo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERNO_SECRET", "")
    get_settings.cache_clear()
    assert (
        client.post(DESPACHAR, headers={"Authorization": "Bearer "}).status_code == 401
    )


def test_envia_los_vencidos_una_sola_vez(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    tid = nuevo_id()
    vincular(client, ana, telegram, tid)
    id_ = programar(client, ana, titulo="Entregar proyecto")
    antes = len(telegram.enviados)
    primera = client.post(DESPACHAR, headers=INTERNO)
    assert primera.status_code == 200, primera.text
    assert primera.json()["enviados"] >= 1
    nuevos = telegram.enviados[antes:]
    assert any(c == tid and "Entregar proyecto" in t for c, t, _ in nuevos)
    resultado = estado(client, ana, id_)
    assert resultado["estado_envio"] == "enviado"
    assert resultado["intentos"] == 1
    assert resultado["enviado_en"] is not None
    enviados = len(telegram.enviados)
    client.post(DESPACHAR, headers=INTERNO)
    assert len(telegram.enviados) == enviados


def test_no_envia_los_futuros_ni_los_cancelados(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    vincular(client, ana, telegram, nuevo_id())
    futuro = programar(client, ana, minutos=60)
    cancelado = programar(client, ana, minutos=-5)
    client.patch(
        f"{RECORDATORIOS}/{cancelado}",
        json={"estado_envio": "cancelado"},
        headers=ana.headers,
    )
    client.post(DESPACHAR, headers=INTERNO)
    assert estado(client, ana, futuro)["estado_envio"] == "pendiente"
    assert estado(client, ana, cancelado)["estado_envio"] == "cancelado"
    assert estado(client, ana, cancelado)["intentos"] == 0


def test_despacha_a_varios_usuarios_cada_uno_a_su_chat(
    client: TestClient, telegram: TelegramFalso, ana: Sesion, beto: Sesion
) -> None:
    tid_ana, tid_beto = nuevo_id(), nuevo_id()
    vincular(client, ana, telegram, tid_ana)
    vincular(client, beto, telegram, tid_beto)
    programar(client, ana, titulo="Cosa de Ana")
    programar(client, beto, titulo="Cosa de Beto")
    client.post(DESPACHAR, headers=INTERNO)
    assert any("Cosa de Ana" in t for t in telegram.textos(tid_ana))
    assert not any("Cosa de Beto" in t for t in telegram.textos(tid_ana))
    assert any("Cosa de Beto" in t for t in telegram.textos(tid_beto))


def test_un_usuario_sin_telegram_queda_como_fallido(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    id_ = programar(client, ana)
    client.post(DESPACHAR, headers=INTERNO)
    assert estado(client, ana, id_)["estado_envio"] == "fallido"
    assert telegram.enviados == []


def test_reintenta_y_se_rinde_al_tercer_fallo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    vincular(client, ana, telegram, nuevo_id())
    id_ = programar(client, ana)
    telegram.fallar = True
    client.post(DESPACHAR, headers=INTERNO)
    assert estado(client, ana, id_)["estado_envio"] == "pendiente"
    assert estado(client, ana, id_)["intentos"] == 1
    client.post(DESPACHAR, headers=INTERNO)
    cierre = client.post(DESPACHAR, headers=INTERNO)
    assert cierre.json()["fallidos"] >= 1
    final = estado(client, ana, id_)
    assert final["estado_envio"] == "fallido" and final["intentos"] == 3
    client.post(DESPACHAR, headers=INTERNO)
    assert estado(client, ana, id_)["intentos"] == 3


def test_un_fallo_se_recupera_en_el_siguiente_ciclo(
    client: TestClient, telegram: TelegramFalso, ana: Sesion
) -> None:
    vincular(client, ana, telegram, nuevo_id())
    id_ = programar(client, ana)
    telegram.fallar = True
    client.post(DESPACHAR, headers=INTERNO)
    telegram.fallar = False
    client.post(DESPACHAR, headers=INTERNO)
    final = estado(client, ana, id_)
    assert final["estado_envio"] == "enviado" and final["intentos"] == 2
