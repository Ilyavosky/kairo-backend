from dataclasses import dataclass
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.core.config import Settings

PASSWORD = "contrasena-segura"


@dataclass(frozen=True)
class Sesion:
    id: str
    email: str
    headers: dict[str, str]


def crear_sesion(client: TestClient) -> Sesion:
    email = f"{uuid4().hex}@prueba.mx"
    registro = client.post(
        "/api/v1/auth/registro",
        json={"email": email, "password": PASSWORD, "nombre": "Prueba"},
    )
    assert registro.status_code == 201
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return Sesion(id=registro.json()["id"], email=email, headers=headers)


def categoria_id(client: TestClient, sesion: Sesion, nombre: str = "Tarea") -> str:
    respuesta = client.get("/api/v1/categorias", headers=sesion.headers)
    assert respuesta.status_code == 200
    for categoria in respuesta.json():
        if categoria["nombre"] == nombre and categoria["del_sistema"]:
            return str(categoria["id"])
    raise AssertionError(f"no existe la categoria {nombre}")


def ejecutar_como_administrador(
    consulta: str, parametros: tuple[object, ...] = ()
) -> None:
    with psycopg.connect(Settings().database_url, autocommit=True) as conn:
        conn.execute(consulta, parametros)
