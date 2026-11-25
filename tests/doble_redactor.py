from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.reportes.router import get_redactor
from app.services.resumen import RedaccionNoDisponible


class RedactorFalso:
    modelo = "redactor-falso"

    def __init__(self, texto: str | None = None, falla: str | None = None) -> None:
        self.texto = texto
        self.falla = falla
        self.recibidas: list[dict[str, Any]] = []

    async def redactar(self, cifras: dict[str, Any]) -> str:
        self.recibidas.append(cifras)
        if self.falla is not None:
            raise RedaccionNoDisponible(self.falla)
        assert self.texto is not None
        return self.texto


def usar_redactor(client: TestClient, redactor: RedactorFalso) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_redactor] = lambda: redactor
