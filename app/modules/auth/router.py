from fastapi import APIRouter, Request

from app.core.auth import Ctx
from app.core.config import get_settings
from app.core.db import Tx
from app.core.errors import ErrorApi
from app.core.limites import verificar
from app.modules.auth import repository, service
from app.modules.auth.schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registro", status_code=201)
async def registro(datos: RegistroIn, tx: Tx) -> UsuarioOut:
    return await service.registrar_usuario(tx, datos)


@router.post("/login")
async def login(datos: LoginIn, tx: Tx, request: Request) -> TokenOut:
    settings = get_settings()
    origen = request.client.host if request.client else "desconocido"
    verificar("login_ip", origen, settings.limite_login_por_min * 3)
    verificar("login_correo", datos.email.lower(), settings.limite_login_por_min)
    return await service.iniciar_sesion(tx, datos, settings)


@router.get("/yo")
async def yo(ctx: Ctx) -> UsuarioOut:
    fila = await repository.obtener_usuario(ctx.conn, ctx.usuario_id)
    if fila is None:
        raise ErrorApi(401, "token_invalido", "La cuenta del token ya no existe")
    return UsuarioOut.model_validate(fila)
