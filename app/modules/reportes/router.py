from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.auth import Ctx
from app.core.config import get_settings
from app.modules.reportes import repository, service
from app.modules.reportes.schemas import (
    AgendaItem,
    CargaDescansoItem,
    CargaSemanalItem,
    MetaProgresoItem,
    PipelineItem,
    ResumenOut,
)
from app.services.resumen import Redactor, crear_redactor

router = APIRouter(prefix="/reportes", tags=["reportes"])


def get_redactor() -> Redactor:
    return crear_redactor(get_settings())


RedactorDep = Annotated[Redactor, Depends(get_redactor)]


@router.get("/agenda")
async def agenda(
    ctx: Ctx,
    dias: Annotated[int, Query(ge=1, le=90)] = 7,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AgendaItem]:
    filas = await repository.agenda(ctx.conn, dias, limite)
    return [AgendaItem.model_validate(f) for f in filas]


@router.get("/carga-semanal")
async def carga_semanal(
    ctx: Ctx,
    semanas_atras: Annotated[int, Query(ge=0, le=52)] = 3,
    semanas_adelante: Annotated[int, Query(ge=0, le=52)] = 4,
) -> list[CargaSemanalItem]:
    filas = await repository.carga_semanal(ctx.conn, semanas_atras, semanas_adelante)
    return [CargaSemanalItem.model_validate(f) for f in filas]


@router.get("/metas")
async def metas(ctx: Ctx) -> list[MetaProgresoItem]:
    filas = await repository.metas(ctx.conn)
    return [MetaProgresoItem.model_validate(f) for f in filas]


@router.get("/pipeline")
async def pipeline(ctx: Ctx) -> list[PipelineItem]:
    filas = await repository.pipeline(ctx.conn)
    return [PipelineItem.model_validate(f) for f in filas]


@router.get("/carga-vs-descanso")
async def carga_vs_descanso(
    ctx: Ctx, semanas: Annotated[int, Query(ge=1, le=52)] = 8
) -> list[CargaDescansoItem]:
    filas = await repository.carga_vs_descanso(ctx.conn, semanas)
    return [CargaDescansoItem.model_validate(f) for f in filas]


@router.get("/resumen")
async def resumen(ctx: Ctx, redactor: RedactorDep) -> ResumenOut:
    return await service.resumen(ctx, redactor)
