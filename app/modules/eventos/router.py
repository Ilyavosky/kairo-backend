from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.eventos import repository
from app.modules.eventos.schemas import EventoIn, EventoOut, EventoPatch

router = APIRouter(prefix="/eventos", tags=["eventos"])


def no_encontrado() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "El evento no existe")


@router.get("")
async def listar(
    ctx: Ctx,
    desde: AwareDatetime | None = None,
    hasta: AwareDatetime | None = None,
    materia_id: UUID | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[EventoOut]:
    filas = await repository.listar(
        ctx.conn, desde, hasta, materia_id, limite, desplazamiento
    )
    return [EventoOut.model_validate(f) for f in filas]


@router.post("", status_code=201)
async def crear(datos: EventoIn, ctx: Ctx) -> EventoOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos)
    return EventoOut.model_validate(fila)


@router.get("/{evento_id}")
async def obtener(evento_id: UUID, ctx: Ctx) -> EventoOut:
    fila = await repository.obtener(ctx.conn, evento_id)
    if fila is None:
        raise no_encontrado()
    return EventoOut.model_validate(fila)


@router.patch("/{evento_id}")
async def actualizar(evento_id: UUID, datos: EventoPatch, ctx: Ctx) -> EventoOut:
    fila = await repository.actualizar(
        ctx.conn, evento_id, datos.model_dump(exclude_unset=True)
    )
    if fila is None:
        raise no_encontrado()
    return EventoOut.model_validate(fila)
