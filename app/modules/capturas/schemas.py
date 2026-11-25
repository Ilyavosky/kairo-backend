from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EntidadTipo = Literal["actividad", "registro_tiempo", "meta"]
EstadoCaptura = Literal["pendiente", "aceptada", "corregida", "descartada"]
Texto = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class CapturaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: Texto


class CorreccionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campos: dict[str, Any] = Field(min_length=1)


class CapturaOut(BaseModel):
    id: UUID
    mensaje: str
    entidad_tipo: EntidadTipo
    estado: EstadoCaptura
    modelo: str
    confianza: float | None
    campos: dict[str, Any]
    pendientes: list[str]
    resultado_id: UUID | None
    creada_en: datetime
    resuelta_en: datetime | None


class MetricaOut(BaseModel):
    entidad_tipo: EntidadTipo
    total: int
    pendientes: int
    aceptadas: int
    corregidas: int
    descartadas: int
    porcentaje_sin_correccion: float | None
    promedio_campos_corregidos: float | None
