from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

Nombre = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class EtiquetaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre


class EtiquetaOut(BaseModel):
    id: UUID
    nombre: str
