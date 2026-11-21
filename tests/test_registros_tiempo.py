from uuid import uuid4

from fastapi.testclient import TestClient

from tests.helpers import (
    Sesion,
    categoria_id,
    categoria_propia,
    crear_actividad,
)

URL = "/api/v1/registros-tiempo"
INICIO = "2026-11-23T09:00:00-06:00"
FIN = "2026-11-23T10:00:00-06:00"


def crear(client: TestClient, sesion: Sesion, **extra: object) -> dict[str, object]:
    cuerpo = {
        "categoria_id": categoria_id(client, sesion, "Estudio"),
        "inicio": INICIO,
        "fin": FIN,
    }
    respuesta = client.post(URL, json={**cuerpo, **extra}, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def test_alta_manual_fija_origen_y_calcula_la_duracion(
    client: TestClient, ana: Sesion
) -> None:
    registro = crear(client, ana, nota="Repaso de redes")
    assert registro["origen"] == "manual"
    assert registro["duracion_s"] == 3600
    assert registro["actividad_id"] is None
    assert registro["nota"] == "Repaso de redes"


def test_fin_igual_o_anterior_al_inicio_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    for fin in (INICIO, "2026-11-23T08:00:00-06:00"):
        respuesta = client.post(
            URL,
            json={
                "categoria_id": categoria_id(client, ana),
                "inicio": INICIO,
                "fin": fin,
            },
            headers=ana.headers,
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "restriccion_violada"


def test_origen_no_se_puede_indicar_desde_la_api(
    client: TestClient, ana: Sesion
) -> None:
    respuesta = client.post(
        URL,
        json={
            "categoria_id": categoria_id(client, ana),
            "inicio": INICIO,
            "fin": FIN,
            "origen": "temporizador",
        },
        headers=ana.headers,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "validacion"


def test_actividad_propia_se_acepta_y_la_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    assert crear(client, ana, actividad_id=actividad)["actividad_id"] == actividad
    ajena = client.post(
        URL,
        json={
            "categoria_id": categoria_id(client, beto),
            "inicio": INICIO,
            "fin": FIN,
            "actividad_id": actividad,
        },
        headers=beto.headers,
    )
    assert ajena.status_code == 422
    assert ajena.json()["codigo"] == "referencia_invalida"


def test_categoria_inexistente_o_propia_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    secreta = categoria_propia(client, ana)
    for categoria in (str(uuid4()), secreta):
        respuesta = client.post(
            URL,
            json={"categoria_id": categoria, "inicio": INICIO, "fin": FIN},
            headers=beto.headers,
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "referencia_invalida"


def test_listado_por_rango_y_categoria_del_mas_reciente_al_mas_antiguo(
    client: TestClient, ana: Sesion
) -> None:
    antiguo = crear(client, ana)
    reciente = crear(
        client,
        ana,
        inicio="2026-11-24T09:00:00-06:00",
        fin="2026-11-24T09:30:00-06:00",
    )
    otra = crear(
        client,
        ana,
        categoria_id=categoria_id(client, ana, "Ejercicio"),
        inicio="2026-11-24T18:00:00-06:00",
        fin="2026-11-24T19:00:00-06:00",
    )

    def ids(**parametros: str) -> list[object]:
        respuesta = client.get(URL, params=parametros, headers=ana.headers)
        assert respuesta.status_code == 200
        return [r["id"] for r in respuesta.json()]

    assert ids() == [otra["id"], reciente["id"], antiguo["id"]]
    assert ids(desde="2026-11-24T00:00:00-06:00") == [otra["id"], reciente["id"]]
    assert ids(hasta="2026-11-23T23:59:00-06:00") == [antiguo["id"]]
    estudio = categoria_id(client, ana, "Estudio")
    assert ids(categoria_id=estudio) == [reciente["id"], antiguo["id"]]


def test_filtro_por_actividad(client: TestClient, ana: Sesion) -> None:
    actividad = crear_actividad(client, ana)
    con_actividad = crear(client, ana, actividad_id=actividad)
    crear(client, ana)
    respuesta = client.get(URL, params={"actividad_id": actividad}, headers=ana.headers)
    assert [r["id"] for r in respuesta.json()] == [con_actividad["id"]]


def test_patch_edita_y_permite_quitar_actividad_y_nota(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    registro = crear(client, ana, actividad_id=actividad, nota="borrador")
    url = f"{URL}/{registro['id']}"
    cambio = client.patch(
        url,
        json={"actividad_id": None, "nota": None, "fin": "2026-11-23T10:30:00-06:00"},
        headers=ana.headers,
    )
    assert cambio.status_code == 200
    assert cambio.json()["actividad_id"] is None
    assert cambio.json()["nota"] is None
    assert cambio.json()["duracion_s"] == 5400


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
    nulo = client.patch(url, json={"categoria_id": None}, headers=ana.headers)
    assert nulo.status_code == 422
    assert nulo.json()["codigo"] == "campo_no_nulo"


def test_registros_sin_token_responden_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401


def test_un_usuario_no_ve_ni_edita_registros_ajenos(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    assert client.get(URL, headers=beto.headers).json() == []
    assert client.get(url, headers=beto.headers).status_code == 404
    assert (
        client.patch(url, json={"nota": "robada"}, headers=beto.headers).status_code
        == 404
    )
