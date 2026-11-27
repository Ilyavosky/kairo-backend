import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.core.auth import Ctx
from app.core.config import get_settings
from app.core.errors import ErrorApi
from app.modules.capturas.router import ExtractorDep
from app.modules.reportes.router import RedactorDep
from app.modules.telegram import bot, repository
from app.modules.telegram.codigos import VIGENCIA_MINUTOS, generar_codigo, hash_codigo
from app.modules.telegram.schemas import ActualizacionTelegram, VinculoOut
from app.services.telegram import ClienteTelegram, crear_cliente

router = APIRouter(prefix="/telegram", tags=["telegram"])


def get_telegram() -> ClienteTelegram:
    return crear_cliente(get_settings())


TelegramDep = Annotated[ClienteTelegram, Depends(get_telegram)]


def verificar_secreto(
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> None:
    esperado = get_settings().telegram_webhook_secret
    recibido = x_telegram_bot_api_secret_token or ""
    if not esperado or not hmac.compare_digest(recibido.encode(), esperado.encode()):
        raise ErrorApi(401, "secreto_invalido", "Secreto de webhook inválido")


@router.post("/vinculo", status_code=201)
async def crear_vinculo(ctx: Ctx) -> VinculoOut:
    codigo = generar_codigo()
    expira = await repository.crear_vinculo(
        ctx.conn, ctx.usuario_id, hash_codigo(codigo), VIGENCIA_MINUTOS
    )
    return VinculoOut(codigo=codigo, comando=f"/vincular {codigo}", expira_en=expira)


@router.post("/webhook", dependencies=[Depends(verificar_secreto)])
async def webhook(
    actualizacion: ActualizacionTelegram,
    request: Request,
    extractor: ExtractorDep,
    redactor: RedactorDep,
    telegram: TelegramDep,
) -> dict[str, bool]:
    await bot.procesar(
        request.app.state.pool, extractor, redactor, telegram, actualizacion
    )
    return {"ok": True}
