from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Estado = Literal["pendiente", "en_progreso", "completada", "cancelada"]
Modalidad = Literal["presencial", "en_linea", "mixta"]
Titulo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Prioridad = Annotated[int, Field(ge=1, le=5)]


class ActividadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo
    descripcion: str | None = Field(default=None, max_length=2000)
    vence_en: AwareDatetime | None = None
    prioridad: Prioridad = 3
    modalidad: Modalidad = "presencial"
    materia_id: UUID | None = None
    categoria_id: UUID


class ActividadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo | None = None
    descripcion: str | None = Field(default=None, max_length=2000)
    vence_en: AwareDatetime | None = None
    prioridad: Prioridad | None = None
    modalidad: Modalidad | None = None
    estado: Estado | None = None
    materia_id: UUID | None = None
    categoria_id: UUID | None = None


class ActividadOut(BaseModel):
    id: UUID
    materia_id: UUID | None
    categoria_id: UUID
    titulo: str
    descripcion: str | None
    vence_en: datetime | None
    prioridad: int
    modalidad: Modalidad
    estado: Estado
    creada_en: datetime
    completada_en: datetime | None
