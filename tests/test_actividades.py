from datetime import datetime

from fastapi.testclient import TestClient

from tests.helpers import Sesion, categoria_id, ejecutar_como_administrador

URL = "/api/v1/actividades"
MATERIAS = "/api/v1/materias"


def crear(client: TestClient, sesion: Sesion, **extra: object) -> dict[str, object]:
    cuerpo = {
        "titulo": "Entregar reporte",
        "categoria_id": categoria_id(client, sesion),
    }
    respuesta = client.post(URL, json={**cuerpo, **extra}, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def crear_materia(client: TestClient, sesion: Sesion) -> str:
    respuesta = client.post(
        MATERIAS, json={"nombre": "Redes", "periodo": "2026-3"}, headers=sesion.headers
    )
    return str(respuesta.json()["id"])


def test_crear_actividad_usa_valores_por_defecto(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear(client, ana)
    assert actividad["estado"] == "pendiente"
    assert actividad["prioridad"] == 3
    assert actividad["modalidad"] == "presencial"
    assert actividad["completada_en"] is None


def test_crear_actividad_con_materia_y_vencimiento(
    client: TestClient, ana: Sesion
) -> None:
    materia = crear_materia(client, ana)
    actividad = crear(
        client,
        ana,
        materia_id=materia,
        vence_en="2026-11-20T18:00:00-06:00",
        prioridad=5,
    )
    assert actividad["materia_id"] == materia
    esperado = datetime.fromisoformat("2026-11-20T18:00:00-06:00")
    assert datetime.fromisoformat(str(actividad["vence_en"])) == esperado


def test_vencimiento_sin_zona_horaria_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    respuesta = client.post(
        URL,
        json={
            "titulo": "x",
            "categoria_id": categoria_id(client, ana),
            "vence_en": "2026-11-20T18:00:00",
        },
        headers=ana.headers,
    )
    assert respuesta.status_code == 422


def test_prioridad_fuera_de_rango_responde_422(client: TestClient, ana: Sesion) -> None:
    respuesta = client.post(
        URL,
        json={"titulo": "x", "categoria_id": categoria_id(client, ana), "prioridad": 6},
        headers=ana.headers,
    )
    assert respuesta.status_code == 422


def test_categoria_inexistente_responde_422(client: TestClient, ana: Sesion) -> None:
    respuesta = client.post(
        URL,
        json={"titulo": "x", "categoria_id": "00000000-0000-0000-0000-000000000000"},
        headers=ana.headers,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "referencia_invalida"


def test_materia_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    materia_de_ana = crear_materia(client, ana)
    respuesta = client.post(
        URL,
        json={
            "titulo": "x",
            "categoria_id": categoria_id(client, beto),
            "materia_id": materia_de_ana,
        },
        headers=beto.headers,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "referencia_invalida"


def test_categoria_propia_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    ejecutar_como_administrador(
        "insert into categoria_actividad (usuario_id, nombre, ambito) "
        "values (%s, 'Secreta', 'personal')",
        (ana.id,),
    )
    categorias = client.get("/api/v1/categorias", headers=ana.headers).json()
    secreta = next(c["id"] for c in categorias if c["nombre"] == "Secreta")
    assert all(
        c["nombre"] != "Secreta"
        for c in client.get("/api/v1/categorias", headers=beto.headers).json()
    )
    respuesta = client.post(
        URL, json={"titulo": "x", "categoria_id": secreta}, headers=beto.headers
    )
    assert respuesta.status_code == 422


def test_completar_fija_completada_en_y_es_idempotente(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear(client, ana)
    url = f"{URL}/{actividad['id']}/completar"
    primera = client.post(url, headers=ana.headers).json()
    assert primera["estado"] == "completada"
    assert primera["completada_en"] is not None
    segunda = client.post(url, headers=ana.headers).json()
    assert segunda["completada_en"] == primera["completada_en"]


def test_reabrir_limpia_completada_en(client: TestClient, ana: Sesion) -> None:
    actividad = crear(client, ana)
    url = f"{URL}/{actividad['id']}"
    client.post(f"{url}/completar", headers=ana.headers)
    reabierta = client.patch(
        url, json={"estado": "pendiente"}, headers=ana.headers
    ).json()
    assert reabierta["completada_en"] is None


def test_patch_cambia_campos_y_permite_quitar_la_materia(
    client: TestClient, ana: Sesion
) -> None:
    materia = crear_materia(client, ana)
    actividad = crear(client, ana, materia_id=materia)
    url = f"{URL}/{actividad['id']}"
    cambio = client.patch(
        url, json={"titulo": "Nuevo titulo", "materia_id": None}, headers=ana.headers
    ).json()
    assert cambio["titulo"] == "Nuevo titulo"
    assert cambio["materia_id"] is None


def test_filtros_y_paginacion(client: TestClient, ana: Sesion) -> None:
    materia = crear_materia(client, ana)
    crear(
        client,
        ana,
        titulo="A",
        vence_en="2026-11-20T12:00:00+00:00",
        materia_id=materia,
    )
    crear(client, ana, titulo="B", vence_en="2026-11-25T12:00:00+00:00")
    hecha = crear(client, ana, titulo="C", vence_en="2026-11-30T12:00:00+00:00")
    client.post(f"{URL}/{hecha['id']}/completar", headers=ana.headers)

    def titulos(**params: object) -> list[str]:
        respuesta = client.get(URL, params=params, headers=ana.headers)
        assert respuesta.status_code == 200
        return [a["titulo"] for a in respuesta.json()]

    assert titulos() == ["A", "B", "C"]
    assert titulos(estado="completada") == ["C"]
    assert titulos(materia_id=materia) == ["A"]
    assert titulos(
        desde="2026-11-22T00:00:00+00:00", hasta="2026-11-27T00:00:00+00:00"
    ) == ["B"]
    assert titulos(limite=1, desplazamiento=1) == ["B"]


def test_limite_invalido_responde_422(client: TestClient, ana: Sesion) -> None:
    assert client.get(URL, params={"limite": 0}, headers=ana.headers).status_code == 422
    assert (
        client.get(URL, params={"estado": "otro"}, headers=ana.headers).status_code
        == 422
    )


def test_un_usuario_no_ve_edita_ni_completa_actividades_ajenas(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    actividad = crear(client, ana)
    url = f"{URL}/{actividad['id']}"
    assert client.get(URL, headers=beto.headers).json() == []
    assert client.get(url, headers=beto.headers).status_code == 404
    assert (
        client.patch(url, json={"titulo": "robada"}, headers=beto.headers).status_code
        == 404
    )
    assert client.post(f"{url}/completar", headers=beto.headers).status_code == 404
    intacta = client.get(url, headers=ana.headers).json()
    assert intacta["titulo"] == "Entregar reporte"
    assert intacta["estado"] == "pendiente"
