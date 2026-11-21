from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

Tipo = Literal["tiempo_acumulado", "numero_eventos"]
Periodo = Literal["dia", "semana", "mes"]
Objetivo = Annotated[int, Field(ge=1, le=100000)]


class MetaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID
    tipo: Tipo
    periodo: Periodo
    objetivo: Objetivo
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class MetaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objetivo: Objetivo | None = None
    vigente_hasta: date | None = None
    activa: bool | None = None


class MetaOut(BaseModel):
    id: UUID
    categoria_id: UUID
    tipo: Tipo
    periodo: Periodo
    objetivo: int
    vigente_desde: date
    vigente_hasta: date | None
    activa: bool
    creada_en: datetime


class ProgresoOut(BaseModel):
    meta_id: UUID
    tipo: Tipo
    periodo: Periodo
    objetivo: int
    periodo_desde: datetime
    periodo_hasta: datetime
    progreso: float
    cumplida: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def porcentaje(self) -> float:
        return round(self.progreso / self.objetivo * 100, 1)


class EvaluacionOut(BaseModel):
    id: UUID
    meta_id: UUID
    periodo_desde: datetime
    periodo_hasta: datetime
    objetivo: int
    valor_logrado: float
    cumplida: bool
    evaluada_en: datetime
