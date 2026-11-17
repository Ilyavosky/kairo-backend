from datetime import datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

Nombre = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class RegistroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nombre: Nombre
    zona_horaria: str = "America/Mexico_City"

    @field_validator("zona_horaria")
    @classmethod
    def zona_valida(cls, valor: str) -> str:
        try:
            ZoneInfo(valor)
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError("zona horaria IANA no reconocida") from exc
        return valor


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioOut(BaseModel):
    id: UUID
    email: str
    nombre: str
    zona_horaria: str
    telegram_id: int | None
    fecha_registro: datetime
    activo: bool
