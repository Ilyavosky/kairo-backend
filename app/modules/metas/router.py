from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.metas import repository
from app.modules.metas.schemas import (
    EvaluacionOut,
    MetaIn,
    MetaOut,
    MetaPatch,
    ProgresoOut,
)

router = APIRouter(prefix="/metas", tags=["metas"])


def no_encontrada() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "La meta no existe")


@router.get("")
async def listar(
    ctx: Ctx, activa: bool | None = None, categoria_id: UUID | None = None
) -> list[MetaOut]:
    filas = await repository.listar(ctx.conn, activa, categoria_id)
    return [MetaOut.model_validate(f) for f in filas]


@router.post("", status_code=201)
async def crear(datos: MetaIn, ctx: Ctx) -> MetaOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos)
    return MetaOut.model_validate(fila)


@router.get("/historial")
async def historial(
    ctx: Ctx,
    meta_id: UUID | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[EvaluacionOut]:
    filas = await repository.historial(ctx.conn, meta_id, limite, desplazamiento)
    return [EvaluacionOut.model_validate(f) for f in filas]


@router.get("/{meta_id}")
async def obtener(meta_id: UUID, ctx: Ctx) -> MetaOut:
    fila = await repository.obtener(ctx.conn, meta_id)
    if fila is None:
        raise no_encontrada()
    return MetaOut.model_validate(fila)


@router.patch("/{meta_id}")
async def actualizar(meta_id: UUID, datos: MetaPatch, ctx: Ctx) -> MetaOut:
    fila = await repository.actualizar(
        ctx.conn, meta_id, datos.model_dump(exclude_unset=True)
    )
    if fila is None:
        raise no_encontrada()
    return MetaOut.model_validate(fila)


@router.get("/{meta_id}/progreso")
async def progreso(meta_id: UUID, ctx: Ctx) -> ProgresoOut:
    fila = await repository.progreso(ctx.conn, meta_id)
    if fila is None:
        raise no_encontrada()
    return ProgresoOut.model_validate(fila)
