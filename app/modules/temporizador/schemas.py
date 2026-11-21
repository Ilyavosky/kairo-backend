from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EstadoSesion = Literal["en_curso", "cerrada"]


class IniciarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID
    actividad_id: UUID | None = None


class DetenerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nota: str | None = Field(default=None, max_length=2000)


class SesionOut(BaseModel):
    id: UUID
    categoria_id: UUID
    actividad_id: UUID | None
    iniciada_en: datetime
    estado: EstadoSesion
    cerrada_en: datetime | None
    registro_tiempo_id: UUID | None
    transcurrido_s: int
