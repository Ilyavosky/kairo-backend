from fastapi import APIRouter

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.registros_tiempo.schemas import RegistroOut
from app.modules.temporizador import repository
from app.modules.temporizador.schemas import DetenerIn, IniciarIn, SesionOut

router = APIRouter(prefix="/temporizador", tags=["temporizador"])


@router.post("/iniciar", status_code=201)
async def iniciar(datos: IniciarIn, ctx: Ctx) -> SesionOut:
    fila = await repository.iniciar(
        ctx.conn, ctx.usuario_id, datos.categoria_id, datos.actividad_id
    )
    if fila is None:
        raise ErrorApi(409, "temporizador_en_curso", "Ya hay un temporizador en curso")
    return SesionOut.model_validate(fila)


@router.post("/detener")
async def detener(ctx: Ctx, datos: DetenerIn | None = None) -> RegistroOut:
    nota = datos.nota if datos is not None else None
    fila = await repository.detener(ctx.conn, ctx.usuario_id, nota)
    if fila is None:
        raise ErrorApi(404, "sin_temporizador", "No hay un temporizador en curso")
    return RegistroOut.model_validate(fila)


@router.get("/actual")
async def actual(ctx: Ctx) -> SesionOut:
    fila = await repository.actual(ctx.conn)
    if fila is None:
        raise ErrorApi(404, "sin_temporizador", "No hay un temporizador en curso")
    return SesionOut.model_validate(fila)
