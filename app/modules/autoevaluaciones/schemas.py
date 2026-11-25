from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Escala = Annotated[int, Field(ge=1, le=5)]


class AutoevaluacionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado_animo: Escala
    satisfaccion: Escala
    nota: str | None = Field(default=None, max_length=2000)


class AutoevaluacionOut(BaseModel):
    semana_desde: date
    estado_animo: int
    satisfaccion: int
    nota: str | None
    creada_en: datetime
    actualizada_en: datetime
