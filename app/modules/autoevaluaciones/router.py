from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.autoevaluaciones import repository
from app.modules.autoevaluaciones.schemas import AutoevaluacionIn, AutoevaluacionOut

router = APIRouter(prefix="/autoevaluaciones", tags=["autoevaluaciones"])


@router.get("")
async def listar(
    ctx: Ctx, limite: Annotated[int, Query(ge=1, le=52)] = 12
) -> list[AutoevaluacionOut]:
    filas = await repository.listar(ctx.conn, limite)
    return [AutoevaluacionOut.model_validate(f) for f in filas]


@router.get("/{semana}")
async def obtener(semana: date, ctx: Ctx) -> AutoevaluacionOut:
    fila = await repository.obtener(ctx.conn, semana)
    if fila is None:
        raise ErrorApi(404, "no_encontrado", "No hay autoevaluación para esa semana")
    return AutoevaluacionOut.model_validate(fila)


@router.put("/{semana}")
async def guardar(semana: date, datos: AutoevaluacionIn, ctx: Ctx) -> AutoevaluacionOut:
    if semana.isoweekday() != 1:
        raise ErrorApi(422, "semana_invalida", "La semana se identifica por su lunes")
    if semana > await repository.hoy_local(ctx.conn, ctx.usuario_id):
        raise ErrorApi(
            422, "semana_futura", "No se puede evaluar una semana que no ha empezado"
        )
    fila = await repository.guardar(
        ctx.conn,
        ctx.usuario_id,
        semana,
        datos.estado_animo,
        datos.satisfaccion,
        datos.nota,
    )
    return AutoevaluacionOut.model_validate(fila)
