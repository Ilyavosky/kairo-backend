from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.recordatorios import repository
from app.modules.recordatorios.schemas import (
    RecordatorioIn,
    RecordatorioOut,
    RecordatorioPatch,
)

router = APIRouter(prefix="/recordatorios", tags=["recordatorios"])


def no_encontrado() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "El recordatorio no existe")


@router.get("")
async def listar(
    ctx: Ctx,
    estado: Literal["pendiente", "enviado", "fallido", "cancelado"] | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[RecordatorioOut]:
    filas = await repository.listar(
        ctx.conn, estado, desde, hasta, limite, desplazamiento
    )
    return [RecordatorioOut.model_validate(f) for f in filas]


@router.post("", status_code=201)
async def crear(datos: RecordatorioIn, ctx: Ctx) -> RecordatorioOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos)
    return RecordatorioOut.model_validate(fila)


@router.get("/{recordatorio_id}")
async def obtener(recordatorio_id: UUID, ctx: Ctx) -> RecordatorioOut:
    fila = await repository.obtener(ctx.conn, recordatorio_id)
    if fila is None:
        raise no_encontrado()
    return RecordatorioOut.model_validate(fila)


@router.patch("/{recordatorio_id}")
async def actualizar(
    recordatorio_id: UUID, datos: RecordatorioPatch, ctx: Ctx
) -> RecordatorioOut:
    fila = await repository.actualizar(
        ctx.conn, recordatorio_id, datos.model_dump(exclude_unset=True)
    )
    if fila is None:
        existente = await repository.obtener(ctx.conn, recordatorio_id)
        if existente is None:
            raise no_encontrado()
        raise ErrorApi(
            409,
            "recordatorio_cerrado",
            "El recordatorio ya no está pendiente y no se puede modificar",
        )
    return RecordatorioOut.model_validate(fila)
