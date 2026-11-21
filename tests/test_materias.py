from fastapi.testclient import TestClient

from tests.helpers import Sesion

URL = "/api/v1/materias"


def crear(
    client: TestClient, sesion: Sesion, nombre: str = "Redes"
) -> dict[str, object]:
    respuesta = client.post(
        URL, json={"nombre": nombre, "periodo": "2026-3"}, headers=sesion.headers
    )
    assert respuesta.status_code == 201
    cuerpo: dict[str, object] = respuesta.json()
    return cuerpo


def test_crear_y_listar_materias(client: TestClient, ana: Sesion) -> None:
    crear(client, ana, "Redes")
    crear(client, ana, "Bases de datos")
    nombres = [m["nombre"] for m in client.get(URL, headers=ana.headers).json()]
    assert nombres == ["Bases de datos", "Redes"]


def test_nombre_repetido_del_mismo_usuario_responde_409(
    client: TestClient, ana: Sesion
) -> None:
    crear(client, ana)
    repetida = client.post(
        URL, json={"nombre": "Redes", "periodo": "2026-3"}, headers=ana.headers
    )
    assert repetida.status_code == 409


def test_dos_usuarios_pueden_tener_la_misma_materia(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    crear(client, ana)
    crear(client, beto)


def test_actualizar_y_dar_de_baja(client: TestClient, ana: Sesion) -> None:
    materia = crear(client, ana)
    url = f"{URL}/{materia['id']}"
    cambio = client.patch(
        url, json={"docente": "Ing. Perez", "activa": False}, headers=ana.headers
    )
    assert cambio.status_code == 200
    assert cambio.json()["docente"] == "Ing. Perez"
    assert client.get(URL, params={"activa": True}, headers=ana.headers).json() == []
    assert (
        len(client.get(URL, params={"activa": False}, headers=ana.headers).json()) == 1
    )


def test_patch_vacio_o_con_nulo_en_campo_obligatorio_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    assert client.patch(url, json={}, headers=ana.headers).status_code == 422
    nulo = client.patch(url, json={"nombre": None}, headers=ana.headers)
    assert nulo.status_code == 422
    assert nulo.json()["codigo"] == "campo_no_nulo"


def test_materias_sin_token_responden_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401


def test_un_usuario_no_ve_ni_edita_materias_ajenas(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    assert client.get(URL, headers=beto.headers).json() == []
    assert client.get(url, headers=beto.headers).status_code == 404
    assert (
        client.patch(url, json={"activa": False}, headers=beto.headers).status_code
        == 404
    )
