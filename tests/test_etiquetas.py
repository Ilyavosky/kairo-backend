from uuid import uuid4

from fastapi.testclient import TestClient

from tests.helpers import Sesion, crear_actividad

URL = "/api/v1/etiquetas"
ACTIVIDADES = "/api/v1/actividades"


def crear(client: TestClient, sesion: Sesion, nombre: str = "Urgente") -> str:
    respuesta = client.post(URL, json={"nombre": nombre}, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


def vinculo(actividad: str, etiqueta: str) -> str:
    return f"{ACTIVIDADES}/{actividad}/etiquetas/{etiqueta}"


def test_crear_y_listar_ordena_sin_distinguir_mayusculas(
    client: TestClient, ana: Sesion
) -> None:
    crear(client, ana, "urgente")
    crear(client, ana, "Escuela")
    nombres = [e["nombre"] for e in client.get(URL, headers=ana.headers).json()]
    assert nombres == ["Escuela", "urgente"]


def test_nombre_repetido_sin_distinguir_mayusculas_responde_409(
    client: TestClient, ana: Sesion
) -> None:
    crear(client, ana, "Urgente")
    repetida = client.post(URL, json={"nombre": "URGENTE"}, headers=ana.headers)
    assert repetida.status_code == 409


def test_dos_usuarios_pueden_tener_la_misma_etiqueta(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    crear(client, ana)
    crear(client, beto)


def test_nombre_vacio_responde_422(client: TestClient, ana: Sesion) -> None:
    respuesta = client.post(URL, json={"nombre": "   "}, headers=ana.headers)
    assert respuesta.status_code == 422


def test_asignar_es_idempotente_y_se_lista_en_la_actividad(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    etiqueta = crear(client, ana)
    for _ in range(2):
        asignada = client.put(vinculo(actividad, etiqueta), headers=ana.headers)
        assert asignada.status_code == 204
    listadas = client.get(f"{ACTIVIDADES}/{actividad}/etiquetas", headers=ana.headers)
    assert [e["id"] for e in listadas.json()] == [etiqueta]


def test_quitar_la_etiqueta_y_volver_a_quitarla_responde_404(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    etiqueta = crear(client, ana)
    client.put(vinculo(actividad, etiqueta), headers=ana.headers)
    assert (
        client.delete(vinculo(actividad, etiqueta), headers=ana.headers).status_code
        == 204
    )
    assert (
        client.delete(vinculo(actividad, etiqueta), headers=ana.headers).status_code
        == 404
    )
    listadas = client.get(f"{ACTIVIDADES}/{actividad}/etiquetas", headers=ana.headers)
    assert listadas.json() == []


def test_etiqueta_o_actividad_inexistente_responde_404(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    etiqueta = crear(client, ana)
    sin_etiqueta = client.put(vinculo(actividad, str(uuid4())), headers=ana.headers)
    sin_actividad = client.put(vinculo(str(uuid4()), etiqueta), headers=ana.headers)
    assert sin_etiqueta.status_code == 404
    assert sin_actividad.status_code == 404


def test_un_usuario_no_puede_mezclar_etiquetas_ni_actividades_ajenas(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    actividad_ana = crear_actividad(client, ana)
    etiqueta_ana = crear(client, ana)
    actividad_beto = crear_actividad(client, beto)
    etiqueta_beto = crear(client, beto)
    assert (
        client.get(URL, headers=beto.headers).json()
        != client.get(URL, headers=ana.headers).json()
    )
    cruzadas = [
        (actividad_ana, etiqueta_beto),
        (actividad_beto, etiqueta_ana),
    ]
    for actividad, etiqueta in cruzadas:
        respuesta = client.put(vinculo(actividad, etiqueta), headers=beto.headers)
        assert respuesta.status_code == 404
    ajena = client.get(f"{ACTIVIDADES}/{actividad_ana}/etiquetas", headers=beto.headers)
    assert ajena.status_code == 404


def test_etiquetas_sin_token_responden_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
