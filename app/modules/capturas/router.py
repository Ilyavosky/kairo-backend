from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Ctx
from app.core.config import get_settings
from app.modules.capturas import repository, service
from app.modules.capturas.schemas import (
    CapturaIn,
    CapturaOut,
    CorreccionIn,
    MetricaOut,
)
from app.services.extraccion import Extractor, crear_extractor

router = APIRouter(prefix="/capturas", tags=["capturas"])


def get_extractor() -> Extractor:
    return crear_extractor(get_settings())


ExtractorDep = Annotated[Extractor, Depends(get_extractor)]


@router.post("", status_code=201)
async def crear(datos: CapturaIn, ctx: Ctx, extractor: ExtractorDep) -> CapturaOut:
    return await service.crear(ctx, extractor, datos.texto)


@router.get("/metricas")
async def metricas(ctx: Ctx) -> list[MetricaOut]:
    filas = await repository.metricas(ctx.conn)
    return [MetricaOut.model_validate(f) for f in filas]


@router.get("/{captura_id}")
async def obtener(captura_id: UUID, ctx: Ctx) -> CapturaOut:
    return await service.obtener(ctx, captura_id)


@router.post("/{captura_id}/confirmar")
async def confirmar(captura_id: UUID, ctx: Ctx) -> CapturaOut:
    return await service.confirmar(ctx, captura_id)


@router.post("/{captura_id}/corregir")
async def corregir(captura_id: UUID, datos: CorreccionIn, ctx: Ctx) -> CapturaOut:
    return await service.corregir(ctx, captura_id, datos.campos)


@router.post("/{captura_id}/descartar")
async def descartar(captura_id: UUID, ctx: Ctx) -> CapturaOut:
    return await service.descartar(ctx, captura_id)
