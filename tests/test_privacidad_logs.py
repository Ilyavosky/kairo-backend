import json
import logging
import random
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.logging import FormatoJson, configurar_logging
from app.services.telegram import ClienteTelegramHttp, TelegramError
from tests.doble_extractor import ExtractorFalso, actividad, usar_extractor
from tests.doble_telegram import (
    SECRETO_WEBHOOK,
    TelegramFalso,
    enviar,
    mensaje,
    usar_telegram,
    vincular,
)
from tests.helpers import Sesion

TOKEN = "123456:TOKEN-SECRETO-DEL-BOT"
TEXTO = "texto-privado-98765 entregar reporte"


class Acumulador(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lineas: list[str] = []
        self.setFormatter(FormatoJson())

    def emit(self, record: logging.LogRecord) -> None:
        self.lineas.append(self.format(record))

    def todo(self) -> str:
        return "\n".join(self.lineas)


@pytest.fixture
def logs() -> Iterator[Acumulador]:
    raiz = logging.getLogger()
    previos = (list(raiz.handlers), raiz.level)
    niveles = {n: logging.getLogger(n).level for n in ("httpx", "httpcore")}
    configurar_logging("INFO")
    acumulador = Acumulador()
    raiz.addHandler(acumulador)
    yield acumulador
    raiz.handlers = previos[0]
    raiz.setLevel(previos[1])
    for nombre, nivel in niveles.items():
        logging.getLogger(nombre).setLevel(nivel)


def cliente_telegram(estado: int) -> ClienteTelegramHttp:
    transporte = httpx.MockTransport(
        lambda _: httpx.Response(estado, json={"ok": True})
    )
    return ClienteTelegramHttp(TOKEN, transport=transporte)


async def test_el_token_del_bot_no_aparece_en_los_logs(logs: Acumulador) -> None:
    await cliente_telegram(200).enviar(1, "hola")
    await cliente_telegram(200).responder_callback("cb")
    assert TOKEN not in logs.todo()
    assert logging.getLogger("httpx").level == logging.WARNING


async def test_el_token_tampoco_sale_en_los_errores(logs: Acumulador) -> None:
    with pytest.raises(TelegramError) as error:
        await cliente_telegram(403).enviar(1, "hola")
    assert TOKEN not in str(error.value)
    assert TOKEN not in logs.todo()


async def test_sin_token_no_se_intenta_enviar() -> None:
    with pytest.raises(TelegramError):
        await ClienteTelegramHttp("").enviar(1, "hola")


@pytest.fixture(autouse=True)
def secreto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRETO_WEBHOOK)


def test_el_texto_de_los_mensajes_no_se_registra(
    client: TestClient, ana: Sesion, logs: Acumulador
) -> None:
    telegram = TelegramFalso()
    usar_telegram(client, telegram)
    tid = random.randint(10**9, 10**10)
    vincular(client, ana, telegram, tid)
    usar_extractor(client, ExtractorFalso(actividad()))
    enviar(client, mensaje(tid, TEXTO))
    client.post("/api/v1/capturas", json={"texto": TEXTO}, headers=ana.headers)
    usar_extractor(client, ExtractorFalso(None))
    enviar(client, mensaje(tid, TEXTO))
    client.post("/api/v1/capturas", json={"texto": TEXTO}, headers=ana.headers)
    registro = logs.todo()
    assert "texto-privado" not in registro
    assert any("POST /api/v1/capturas" in linea for linea in logs.lineas)


def test_un_error_interno_no_vuelca_el_cuerpo_de_la_peticion(
    client: TestClient, ana: Sesion, logs: Acumulador
) -> None:
    usar_extractor(client, ExtractorFalso(actividad(titulo="x" * 300)))
    client.post("/api/v1/capturas", json={"texto": TEXTO}, headers=ana.headers)
    assert "texto-privado" not in logs.todo()


def test_las_lineas_de_log_son_json_valido(
    client: TestClient, ana: Sesion, logs: Acumulador
) -> None:
    client.get("/health")
    assert all(json.loads(linea)["logger"] for linea in logs.lineas)
