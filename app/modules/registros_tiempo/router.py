from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.registros_tiempo import repository
from app.modules.registros_tiempo.schemas import (
    RegistroIn,
    RegistroOut,
    RegistroPatch,
)

router = APIRouter(prefix="/registros-tiempo", tags=["registros-tiempo"])


def no_encontrado() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "El registro de tiempo no existe")


@router.get("")
async def listar(
    ctx: Ctx,
    desde: AwareDatetime | None = None,
    hasta: AwareDatetime | None = None,
    categoria_id: UUID | None = None,
    actividad_id: UUID | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[RegistroOut]:
    filas = await repository.listar(
        ctx.conn, desde, hasta, categoria_id, actividad_id, limite, desplazamiento
    )
    return [RegistroOut.model_validate(f) for f in filas]


@router.post("", status_code=201)
async def crear(datos: RegistroIn, ctx: Ctx) -> RegistroOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos)
    return RegistroOut.model_validate(fila)


@router.get("/{registro_id}")
async def obtener(registro_id: UUID, ctx: Ctx) -> RegistroOut:
    fila = await repository.obtener(ctx.conn, registro_id)
    if fila is None:
        raise no_encontrado()
    return RegistroOut.model_validate(fila)


@router.patch("/{registro_id}")
async def actualizar(registro_id: UUID, datos: RegistroPatch, ctx: Ctx) -> RegistroOut:
    fila = await repository.actualizar(
        ctx.conn, registro_id, datos.model_dump(exclude_unset=True)
    )
    if fila is None:
        raise no_encontrado()
    return RegistroOut.model_validate(fila)
