from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

Texto = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class MateriaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Texto
    docente: Texto | None = None
    clave: Texto | None = None
    periodo: Texto


class MateriaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Texto | None = None
    docente: Texto | None = None
    clave: Texto | None = None
    periodo: Texto | None = None
    activa: bool | None = None


class MateriaOut(BaseModel):
    id: UUID
    nombre: str
    docente: str | None
    clave: str | None
    periodo: str
    activa: bool
