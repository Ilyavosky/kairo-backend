from dataclasses import dataclass

from app.services.telegram import Boton


@dataclass(frozen=True)
class Respuesta:
    texto: str
    botones: list[Boton] | None = None
