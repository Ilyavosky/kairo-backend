from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, computed_field


class AgendaItem(BaseModel):
    tipo: Literal["actividad", "evento"]
    id: UUID
    titulo: str
    materia_id: UUID | None
    materia: str | None
    categoria: str | None
    cuando: datetime
    prioridad: int | None
    estado: str | None
    subtipo: Literal["clase", "examen", "entrega", "reunion", "personal"] | None


class CargaSemanalItem(BaseModel):
    semana_desde: date
    materia_id: UUID | None
    materia: str | None
    actividades_con_vencimiento: int
    actividades_pendientes: int
    minutos_registrados: float


class MetaProgresoItem(BaseModel):
    meta_id: UUID
    categoria_id: UUID
    categoria: str
    tipo: Literal["tiempo_acumulado", "numero_eventos"]
    periodo: Literal["dia", "semana", "mes"]
    objetivo: int
    periodo_desde: datetime
    periodo_hasta: datetime
    progreso: float
    cumplida: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def porcentaje(self) -> float:
        return round(self.progreso / self.objetivo * 100, 1)


class PipelineItem(BaseModel):
    entidad_tipo: Literal["actividad", "registro_tiempo", "meta"]
    total: int
    pendientes: int
    aceptadas: int
    corregidas: int
    descartadas: int
    porcentaje_sin_correccion: float | None
    promedio_campos_corregidos: float | None


class CargaDescansoItem(BaseModel):
    semana_desde: date
    minutos_academicos: float
    minutos_sueno: float
    minutos_ejercicio: float
    estado_animo: int | None
    satisfaccion: int | None


class Cifras(BaseModel):
    agenda: list[AgendaItem]
    carga_semanal: list[CargaSemanalItem]
    metas: list[MetaProgresoItem]
    pipeline: list[PipelineItem]
    carga_vs_descanso: list[CargaDescansoItem]


class ResumenOut(BaseModel):
    generado_en: datetime
    cifras: Cifras
    texto: str | None
    modelo: str | None
    motivo_sin_texto: str | None
