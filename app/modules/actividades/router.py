from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.actividades import repository
from app.modules.actividades.schemas import (
    ActividadIn,
    ActividadOut,
    ActividadPatch,
    Estado,
)

router = APIRouter(prefix="/actividades", tags=["actividades"])


def no_encontrada() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "La actividad no existe")


@router.get("")
async def listar(
    ctx: Ctx,
    estado: Estado | None = None,
    materia_id: UUID | None = None,
    desde: AwareDatetime | None = None,
    hasta: AwareDatetime | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[ActividadOut]:
    filas = await repository.listar(
        ctx.conn, estado, materia_id, desde, hasta, limite, desplazamiento
    )
    return [ActividadOut.model_validate(f) for f in filas]


@router.post("", status_code=201)
async def crear(datos: ActividadIn, ctx: Ctx) -> ActividadOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos)
    return ActividadOut.model_validate(fila)


@router.get("/{actividad_id}")
async def obtener(actividad_id: UUID, ctx: Ctx) -> ActividadOut:
    fila = await repository.obtener(ctx.conn, actividad_id)
    if fila is None:
        raise no_encontrada()
    return ActividadOut.model_validate(fila)


@router.patch("/{actividad_id}")
async def actualizar(
    actividad_id: UUID, datos: ActividadPatch, ctx: Ctx
) -> ActividadOut:
    fila = await repository.actualizar(
        ctx.conn, actividad_id, datos.model_dump(exclude_unset=True)
    )
    if fila is None:
        raise no_encontrada()
    return ActividadOut.model_validate(fila)


@router.post("/{actividad_id}/completar")
async def completar(actividad_id: UUID, ctx: Ctx) -> ActividadOut:
    fila = await repository.actualizar(ctx.conn, actividad_id, {"estado": "completada"})
    if fila is None:
        raise no_encontrada()
    return ActividadOut.model_validate(fila)
