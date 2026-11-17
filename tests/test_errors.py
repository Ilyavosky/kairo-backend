from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from app.core.errors import ErrorApi, registrar_manejadores


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/error-api")
    async def error_api() -> None:
        raise ErrorApi(404, "no_encontrado", "No existe")

    @app.get("/validacion/{numero}")
    async def validacion(numero: int) -> int:
        return numero

    @app.get("/unico")
    async def unico() -> None:
        raise UniqueViolation()

    @app.get("/check")
    async def check() -> None:
        raise CheckViolation()

    @app.get("/referencia")
    async def referencia() -> None:
        raise ForeignKeyViolation()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secreto interno")

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_error_api_usa_el_formato_unico(client: TestClient) -> None:
    response = client.get("/error-api")
    assert response.status_code == 404
    assert response.json() == {"codigo": "no_encontrado", "detalle": "No existe"}


def test_validacion_responde_422_con_formato_unico(client: TestClient) -> None:
    response = client.get("/validacion/abc")
    assert response.status_code == 422
    cuerpo = response.json()
    assert cuerpo["codigo"] == "validacion"
    assert "numero" in cuerpo["detalle"]


@pytest.mark.parametrize(
    ("ruta", "status", "codigo"),
    [
        ("/unico", 409, "conflicto"),
        ("/check", 422, "restriccion_violada"),
        ("/referencia", 422, "referencia_invalida"),
    ],
)
def test_violaciones_de_la_base_se_traducen(
    client: TestClient, ruta: str, status: int, codigo: str
) -> None:
    response = client.get(ruta)
    assert response.status_code == status
    assert response.json()["codigo"] == codigo


def test_error_no_controlado_no_filtra_detalles(client: TestClient) -> None:
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["codigo"] == "error_interno"
    assert "secreto interno" not in response.text
