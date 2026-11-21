from fastapi.testclient import TestClient

from tests.helpers import Sesion

URL = "/api/v1/eventos"
MATERIAS = "/api/v1/materias"
INICIO = "2026-11-23T09:00:00-06:00"
FIN = "2026-11-23T11:00:00-06:00"


def crear(client: TestClient, sesion: Sesion, **extra: object) -> dict[str, object]:
    cuerpo = {"titulo": "Clase de redes", "inicio": INICIO, "fin": FIN}
    respuesta = client.post(URL, json={**cuerpo, **extra}, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def test_crear_y_obtener_evento(client: TestClient, ana: Sesion) -> None:
    evento = crear(client, ana, lugar="Aula 4", descripcion="Unidad 3")
    assert evento["lugar"] == "Aula 4"
    assert evento["materia_id"] is None
    obtenido = client.get(f"{URL}/{evento['id']}", headers=ana.headers)
    assert obtenido.status_code == 200
    assert obtenido.json() == evento


def test_fin_igual_o_anterior_al_inicio_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    for fin in (INICIO, "2026-11-23T08:00:00-06:00"):
        respuesta = client.post(
            URL,
            json={"titulo": "x", "inicio": INICIO, "fin": fin},
            headers=ana.headers,
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "restriccion_violada"


def test_fecha_sin_zona_horaria_responde_422(client: TestClient, ana: Sesion) -> None:
    respuesta = client.post(
        URL,
        json={"titulo": "x", "inicio": "2026-11-23T09:00:00", "fin": FIN},
        headers=ana.headers,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "validacion"


def test_filtro_por_rango_incluye_los_que_se_traslapan(
    client: TestClient, ana: Sesion
) -> None:
    primero = crear(client, ana, titulo="Primero")
    segundo = crear(
        client,
        ana,
        titulo="Segundo",
        inicio="2026-11-23T12:00:00-06:00",
        fin="2026-11-23T13:00:00-06:00",
    )

    def ids(**parametros: str) -> list[object]:
        respuesta = client.get(URL, params=parametros, headers=ana.headers)
        assert respuesta.status_code == 200
        return [e["id"] for e in respuesta.json()]

    assert ids() == [primero["id"], segundo["id"]]
    assert ids(desde="2026-11-23T11:30:00-06:00") == [segundo["id"]]
    assert ids(
        desde="2026-11-23T10:00:00-06:00", hasta="2026-11-23T10:30:00-06:00"
    ) == [primero["id"]]
    assert ids(hasta="2026-11-23T08:00:00-06:00") == []


def test_patch_cambia_campos_y_permite_quitar_el_lugar(
    client: TestClient, ana: Sesion
) -> None:
    evento = crear(client, ana, lugar="Aula 4")
    url = f"{URL}/{evento['id']}"
    cambio = client.patch(
        url, json={"titulo": "Clase movida", "lugar": None}, headers=ana.headers
    )
    assert cambio.status_code == 200
    assert cambio.json()["titulo"] == "Clase movida"
    assert cambio.json()["lugar"] is None


def test_patch_que_deja_fin_antes_del_inicio_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    respuesta = client.patch(
        url, json={"fin": "2026-11-23T08:00:00-06:00"}, headers=ana.headers
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "restriccion_violada"


def test_patch_vacio_o_con_nulo_en_campo_obligatorio_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    assert client.patch(url, json={}, headers=ana.headers).status_code == 422
    nulo = client.patch(url, json={"inicio": None}, headers=ana.headers)
    assert nulo.status_code == 422
    assert nulo.json()["codigo"] == "campo_no_nulo"


def test_materia_propia_se_acepta_y_la_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    materia = client.post(
        MATERIAS, json={"nombre": "Redes", "periodo": "2026-3"}, headers=ana.headers
    ).json()["id"]
    assert crear(client, ana, materia_id=materia)["materia_id"] == materia
    ajena = client.post(
        URL,
        json={"titulo": "x", "inicio": INICIO, "fin": FIN, "materia_id": materia},
        headers=beto.headers,
    )
    assert ajena.status_code == 422
    assert ajena.json()["codigo"] == "referencia_invalida"


def test_eventos_sin_token_responden_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401


def test_un_usuario_no_ve_ni_edita_eventos_ajenos(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    assert client.get(URL, headers=beto.headers).json() == []
    assert client.get(url, headers=beto.headers).status_code == 404
    assert (
        client.patch(url, json={"titulo": "robado"}, headers=beto.headers).status_code
        == 404
    )
