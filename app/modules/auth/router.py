from fastapi import APIRouter

from app.core.auth import Ctx
from app.core.config import get_settings
from app.core.db import Tx
from app.core.errors import ErrorApi
from app.modules.auth import repository, service
from app.modules.auth.schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registro", status_code=201)
async def registro(datos: RegistroIn, tx: Tx) -> UsuarioOut:
    return await service.registrar_usuario(tx, datos)


@router.post("/login")
async def login(datos: LoginIn, tx: Tx) -> TokenOut:
    return await service.iniciar_sesion(tx, datos, get_settings())


@router.get("/yo")
async def yo(ctx: Ctx) -> UsuarioOut:
    fila = await repository.obtener_usuario(ctx.conn, ctx.usuario_id)
    if fila is None:
        raise ErrorApi(401, "token_invalido", "La cuenta del token ya no existe")
    return UsuarioOut.model_validate(fila)
