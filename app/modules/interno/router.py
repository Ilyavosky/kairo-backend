import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import ErrorApi
from app.modules.recordatorios.despacho import ResultadoDespacho, despachar
from app.modules.telegram.router import TelegramDep

esquema = HTTPBearer(auto_error=False)


def verificar_interno(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema)],
) -> None:
    esperado = get_settings().interno_secret
    recibido = credenciales.credentials if credenciales else ""
    if not esperado or not hmac.compare_digest(recibido.encode(), esperado.encode()):
        raise ErrorApi(401, "no_autorizado", "Credencial interna inválida")


router = APIRouter(
    prefix="/interno",
    tags=["interno"],
    include_in_schema=False,
    dependencies=[Depends(verificar_interno)],
)


@router.post("/recordatorios/despachar")
async def despachar_recordatorios(
    request: Request, telegram: TelegramDep
) -> ResultadoDespacho:
    return await despachar(request.app.state.pool, telegram)
