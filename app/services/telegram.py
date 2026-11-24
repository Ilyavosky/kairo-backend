from typing import Any, Protocol

import httpx

from app.core.config import Settings

Boton = tuple[str, str]


class TelegramError(Exception):
    pass


class ClienteTelegram(Protocol):
    async def enviar(
        self, chat_id: int, texto: str, botones: list[Boton] | None = None
    ) -> None: ...

    async def responder_callback(self, callback_id: str) -> None: ...


class ClienteTelegramHttp:
    def __init__(
        self,
        token: str,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._timeout_s = timeout_s
        self._transport = transport

    async def _llamar(self, metodo: str, cuerpo: dict[str, Any]) -> None:
        if not self._token:
            raise TelegramError("sin_token")
        url = f"https://api.telegram.org/bot{self._token}/{metodo}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as http:
                respuesta = await http.post(url, json=cuerpo)
        except httpx.HTTPError as exc:
            raise TelegramError(type(exc).__name__) from exc
        if respuesta.status_code != 200:
            raise TelegramError(f"http_{respuesta.status_code}")

    async def enviar(
        self, chat_id: int, texto: str, botones: list[Boton] | None = None
    ) -> None:
        cuerpo: dict[str, Any] = {"chat_id": chat_id, "text": texto}
        if botones:
            cuerpo["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": etiqueta, "callback_data": dato}
                        for etiqueta, dato in botones
                    ]
                ]
            }
        await self._llamar("sendMessage", cuerpo)

    async def responder_callback(self, callback_id: str) -> None:
        await self._llamar("answerCallbackQuery", {"callback_query_id": callback_id})


def crear_cliente(settings: Settings) -> ClienteTelegram:
    return ClienteTelegramHttp(settings.telegram_bot_token)
