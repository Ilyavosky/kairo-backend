from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.helpers import PASSWORD, Sesion

REGISTRO = "/api/v1/auth/registro"
LOGIN = "/api/v1/auth/login"
YO = "/api/v1/auth/yo"


def datos(**extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": f"{uuid4().hex}@prueba.mx",
        "password": PASSWORD,
        "nombre": "Ilya",
    }
    return {**base, **extra}


def test_registro_crea_el_usuario_sin_exponer_la_contrasena(client: TestClient) -> None:
    respuesta = client.post(REGISTRO, json=datos())
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["zona_horaria"] == "America/Mexico_City"
    assert cuerpo["activo"] is True
    assert "password" not in cuerpo
    assert "password_hash" not in cuerpo


def test_registro_guarda_el_correo_en_minusculas(client: TestClient) -> None:
    correo = f"{uuid4().hex}@Prueba.MX"
    respuesta = client.post(REGISTRO, json=datos(email=correo))
    assert respuesta.json()["email"] == correo.lower()


def test_registro_con_correo_repetido_responde_409(client: TestClient) -> None:
    correo = f"{uuid4().hex}@prueba.mx"
    assert client.post(REGISTRO, json=datos(email=correo)).status_code == 201
    repetido = client.post(REGISTRO, json=datos(email=correo.upper()))
    assert repetido.status_code == 409
    assert repetido.json()["codigo"] == "correo_en_uso"


@pytest.mark.parametrize(
    "cambio",
    [
        {"email": "no-es-correo"},
        {"password": "corta"},
        {"nombre": "   "},
        {"zona_horaria": "Marte/Olimpo"},
        {"campo_extra": "x"},
    ],
)
def test_registro_con_datos_invalidos_responde_422(
    client: TestClient, cambio: dict[str, object]
) -> None:
    respuesta = client.post(REGISTRO, json=datos(**cambio))
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "validacion"


def test_login_devuelve_un_token_que_abre_yo(client: TestClient, ana: Sesion) -> None:
    respuesta = client.get(YO, headers=ana.headers)
    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == ana.id


def test_login_con_contrasena_incorrecta_responde_401(
    client: TestClient, ana: Sesion
) -> None:
    respuesta = client.post(
        LOGIN, json={"email": ana.email, "password": "incorrecta-123"}
    )
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "credenciales_invalidas"


def test_login_con_correo_inexistente_responde_lo_mismo(client: TestClient) -> None:
    respuesta = client.post(
        LOGIN, json={"email": "nadie@prueba.mx", "password": PASSWORD}
    )
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "credenciales_invalidas"


def test_yo_sin_token_responde_401(client: TestClient) -> None:
    respuesta = client.get(YO)
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "no_autenticado"


def test_yo_con_token_manipulado_responde_401(client: TestClient, ana: Sesion) -> None:
    token = ana.headers["Authorization"] + "x"
    respuesta = client.get(YO, headers={"Authorization": token})
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "token_invalido"
