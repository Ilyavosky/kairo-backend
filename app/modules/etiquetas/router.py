from uuid import UUID

from fastapi import APIRouter

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.etiquetas import repository
from app.modules.etiquetas.schemas import EtiquetaIn, EtiquetaOut

router = APIRouter(tags=["etiquetas"])


async def exigir_existencia(ctx: Ctx, actividad_id: UUID, etiqueta_id: UUID) -> None:
    if not await repository.existe_actividad(ctx.conn, actividad_id):
        raise ErrorApi(404, "no_encontrado", "La actividad no existe")
    if not await repository.existe_etiqueta(ctx.conn, etiqueta_id):
        raise ErrorApi(404, "no_encontrado", "La etiqueta no existe")


@router.get("/etiquetas")
async def listar(ctx: Ctx) -> list[EtiquetaOut]:
    filas = await repository.listar(ctx.conn)
    return [EtiquetaOut.model_validate(f) for f in filas]


@router.post("/etiquetas", status_code=201)
async def crear(datos: EtiquetaIn, ctx: Ctx) -> EtiquetaOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos.nombre)
    return EtiquetaOut.model_validate(fila)


@router.get("/actividades/{actividad_id}/etiquetas")
async def de_actividad(actividad_id: UUID, ctx: Ctx) -> list[EtiquetaOut]:
    if not await repository.existe_actividad(ctx.conn, actividad_id):
        raise ErrorApi(404, "no_encontrado", "La actividad no existe")
    filas = await repository.de_actividad(ctx.conn, actividad_id)
    return [EtiquetaOut.model_validate(f) for f in filas]


@router.put("/actividades/{actividad_id}/etiquetas/{etiqueta_id}", status_code=204)
async def asignar(actividad_id: UUID, etiqueta_id: UUID, ctx: Ctx) -> None:
    await exigir_existencia(ctx, actividad_id, etiqueta_id)
    await repository.asignar(ctx.conn, ctx.usuario_id, actividad_id, etiqueta_id)


@router.delete("/actividades/{actividad_id}/etiquetas/{etiqueta_id}", status_code=204)
async def quitar(actividad_id: UUID, etiqueta_id: UUID, ctx: Ctx) -> None:
    if not await repository.quitar(ctx.conn, actividad_id, etiqueta_id):
        raise ErrorApi(404, "no_encontrado", "La actividad no tiene esa etiqueta")
