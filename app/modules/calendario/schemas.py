from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

TipoCalendario = Literal[
    "inicio_periodo", "fin_periodo", "inhabil", "examen", "institucional"
]


class EventoCalendarioOut(BaseModel):
    id: UUID
    periodo: str
    tipo: TipoCalendario
    fecha: date
    fecha_fin: date | None
    descripcion: str
