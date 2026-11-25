from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.telegram.router import get_telegram
from app.services.telegram import Boton, TelegramError
from tests.helpers import Sesion

SECRETO_WEBHOOK = "secreto-de-webhook-de-prueba"
SECRETO_INTERNO = "secreto-interno-de-prueba"
CABECERA = {"X-Telegram-Bot-Api-Secret-Token": SECRETO_WEBHOOK}
INTERNO = {"Authorization": f"Bearer {SECRETO_INTERNO}"}
WEBHOOK = "/api/v1/telegram/webhook"
DESPACHAR = "/api/v1/interno/recordatorios/despachar"


class TelegramFalso:
    def __init__(self) -> None:
        self.enviados: list[tuple[int, str, list[Boton] | None]] = []
        self.callbacks: list[str] = []
        self.fallar = False

    async def enviar(
        self, chat_id: int, texto: str, botones: list[Boton] | None = None
    ) -> None:
        if self.fallar:
            raise TelegramError("http_500")
        self.enviados.append((chat_id, texto, botones))

    async def responder_callback(self, callback_id: str) -> None:
        self.callbacks.append(callback_id)

    def textos(self, chat_id: int) -> list[str]:
        return [t for c, t, _ in self.enviados if c == chat_id]


def usar_telegram(client: TestClient, telegram: TelegramFalso) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_telegram] = lambda: telegram


def mensaje(telegram_id: int, texto: str) -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": telegram_id},
            "from": {"id": telegram_id},
            "text": texto,
        },
    }


def boton(telegram_id: int, dato: str) -> dict[str, object]:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb-1",
            "from": {"id": telegram_id},
            "data": dato,
            "message": {"message_id": 1, "chat": {"id": telegram_id}},
        },
    }


def enviar(
    client: TestClient,
    cuerpo: dict[str, object],
    cabeceras: dict[str, str] | None = None,
) -> int:
    respuesta = client.post(
        WEBHOOK, json=cuerpo, headers=CABECERA if cabeceras is None else cabeceras
    )
    status: int = respuesta.status_code
    return status


def generar_codigo(client: TestClient, sesion: Sesion) -> str:
    respuesta = client.post("/api/v1/telegram/vinculo", headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    codigo: str = respuesta.json()["codigo"]
    return codigo


def vincular(
    client: TestClient, sesion: Sesion, telegram: TelegramFalso, telegram_id: int
) -> None:
    codigo = generar_codigo(client, sesion)
    assert enviar(client, mensaje(telegram_id, f"/vincular {codigo}")) == 200
    assert "vinculada" in telegram.textos(telegram_id)[-1]
