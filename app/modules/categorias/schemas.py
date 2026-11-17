from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Ambito = Literal["academica", "personal", "ambas"]


class CategoriaOut(BaseModel):
    id: UUID
    nombre: str
    ambito: Ambito
    peso_default: float
    del_sistema: bool
