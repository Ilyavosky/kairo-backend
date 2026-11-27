from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Titulo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
TipoEvento = Literal["clase", "examen", "entrega", "reunion", "personal"]
Lugar = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class EventoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo
    descripcion: str | None = Field(default=None, max_length=2000)
    lugar: Lugar | None = None
    inicio: AwareDatetime
    fin: AwareDatetime
    materia_id: UUID | None = None
    tipo: TipoEvento = "personal"
    actividad_id: UUID | None = None


class EventoPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo | None = None
    descripcion: str | None = Field(default=None, max_length=2000)
    lugar: Lugar | None = None
    inicio: AwareDatetime | None = None
    fin: AwareDatetime | None = None
    materia_id: UUID | None = None
    tipo: TipoEvento | None = None
    actividad_id: UUID | None = None


class EventoOut(BaseModel):
    id: UUID
    materia_id: UUID | None
    titulo: str
    descripcion: str | None
    lugar: str | None
    inicio: datetime
    fin: datetime
    tipo: TipoEvento
    actividad_id: UUID | None
    creado_en: datetime
