from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field

Origen = Literal["temporizador", "manual"]


class RegistroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID
    actividad_id: UUID | None = None
    inicio: AwareDatetime
    fin: AwareDatetime
    nota: str | None = Field(default=None, max_length=2000)


class RegistroPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID | None = None
    actividad_id: UUID | None = None
    inicio: AwareDatetime | None = None
    fin: AwareDatetime | None = None
    nota: str | None = Field(default=None, max_length=2000)


class RegistroOut(BaseModel):
    id: UUID
    categoria_id: UUID
    actividad_id: UUID | None
    inicio: datetime
    fin: datetime
    origen: Origen
    nota: str | None
    creado_en: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duracion_s(self) -> int:
        return int((self.fin - self.inicio).total_seconds())
