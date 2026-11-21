from fastapi.testclient import TestClient

from tests.helpers import Sesion, ejecutar_como_administrador


def test_categorias_incluye_las_del_sistema(client: TestClient, ana: Sesion) -> None:
    respuesta = client.get("/api/v1/categorias", headers=ana.headers)
    assert respuesta.status_code == 200
    nombres = {c["nombre"] for c in respuesta.json()}
    assert {"Tarea", "Examen", "Sueno", "Ejercicio"} <= nombres
    assert all(c["del_sistema"] for c in respuesta.json())


def test_categorias_filtra_por_ambito_e_incluye_las_mixtas(
    client: TestClient, ana: Sesion
) -> None:
    personales = client.get(
        "/api/v1/categorias", params={"ambito": "personal"}, headers=ana.headers
    ).json()
    nombres = {c["nombre"] for c in personales}
    assert "Sueno" in nombres
    assert "Estudio" in nombres
    assert "Tarea" not in nombres


def test_categorias_exige_token(client: TestClient) -> None:
    assert client.get("/api/v1/categorias").status_code == 401


def test_calendario_lista_y_filtra(client: TestClient, ana: Sesion) -> None:
    ejecutar_como_administrador(
        "insert into calendario_academico (periodo, tipo, fecha, descripcion) "
        "values ('prueba-2026', 'inhabil', '2026-11-16', 'Revolucion') "
        "on conflict do nothing"
    )
    respuesta = client.get(
        "/api/v1/calendario", params={"periodo": "prueba-2026"}, headers=ana.headers
    )
    assert respuesta.status_code == 200
    assert [e["descripcion"] for e in respuesta.json()] == ["Revolucion"]
    assert (
        client.get(
            "/api/v1/calendario", params={"tipo": "otro"}, headers=ana.headers
        ).status_code
        == 422
    )
