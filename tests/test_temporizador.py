from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import Sesion, categoria_id, categoria_propia, crear_actividad

URL = "/api/v1/temporizador"
REGISTROS = "/api/v1/registros-tiempo"


def iniciar(client: TestClient, sesion: Sesion, **extra: object) -> dict[str, object]:
    cuerpo = {"categoria_id": categoria_id(client, sesion, "Estudio")}
    respuesta = client.post(
        f"{URL}/iniciar", json={**cuerpo, **extra}, headers=sesion.headers
    )
    assert respuesta.status_code == 201, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def test_iniciar_crea_una_sesion_en_curso(client: TestClient, ana: Sesion) -> None:
    sesion = iniciar(client, ana)
    assert sesion["estado"] == "en_curso"
    assert sesion["cerrada_en"] is None
    assert sesion["registro_tiempo_id"] is None
    assert isinstance(sesion["transcurrido_s"], int)
    assert sesion["transcurrido_s"] >= 0


def test_iniciar_dos_veces_seguidas_responde_409(
    client: TestClient, ana: Sesion
) -> None:
    iniciar(client, ana)
    segunda = client.post(
        f"{URL}/iniciar",
        json={"categoria_id": categoria_id(client, ana, "Estudio")},
        headers=ana.headers,
    )
    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "temporizador_en_curso"


def test_actual_devuelve_la_sesion_en_curso(client: TestClient, ana: Sesion) -> None:
    sesion = iniciar(client, ana)
    actual = client.get(f"{URL}/actual", headers=ana.headers)
    assert actual.status_code == 200
    assert actual.json()["id"] == sesion["id"]


def test_actual_sin_sesion_responde_404(client: TestClient, ana: Sesion) -> None:
    actual = client.get(f"{URL}/actual", headers=ana.headers)
    assert actual.status_code == 404
    assert actual.json()["codigo"] == "sin_temporizador"


def test_detener_sin_sesion_responde_404(client: TestClient, ana: Sesion) -> None:
    detenido = client.post(f"{URL}/detener", headers=ana.headers)
    assert detenido.status_code == 404
    assert detenido.json()["codigo"] == "sin_temporizador"


def test_detener_crea_el_registro_y_cierra_la_sesion(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    sesion = iniciar(client, ana, actividad_id=actividad)
    detenido = client.post(
        f"{URL}/detener", json={"nota": "Repaso de redes"}, headers=ana.headers
    )
    assert detenido.status_code == 200
    registro = detenido.json()
    assert registro["origen"] == "temporizador"
    assert registro["categoria_id"] == sesion["categoria_id"]
    assert registro["actividad_id"] == actividad
    assert registro["nota"] == "Repaso de redes"
    assert registro["duracion_s"] >= 0
    assert registro["inicio"] == sesion["iniciada_en"]
    assert client.get(f"{URL}/actual", headers=ana.headers).status_code == 404
    guardado = client.get(f"{REGISTROS}/{registro['id']}", headers=ana.headers)
    assert guardado.status_code == 200
    assert guardado.json()["origen"] == "temporizador"


def test_detener_sin_cuerpo_deja_la_nota_vacia(client: TestClient, ana: Sesion) -> None:
    iniciar(client, ana)
    detenido = client.post(f"{URL}/detener", headers=ana.headers)
    assert detenido.status_code == 200
    assert detenido.json()["nota"] is None


def test_despues_de_detener_se_puede_iniciar_otra_sesion(
    client: TestClient, ana: Sesion
) -> None:
    primera = iniciar(client, ana)
    client.post(f"{URL}/detener", headers=ana.headers)
    segunda = iniciar(client, ana)
    assert segunda["id"] != primera["id"]


def test_la_sesion_vive_en_la_base_y_sobrevive_a_un_reinicio_del_servicio(
    client: TestClient, ana: Sesion
) -> None:
    sesion = iniciar(client, ana)
    with TestClient(create_app()) as servicio_nuevo:
        actual = servicio_nuevo.get(f"{URL}/actual", headers=ana.headers)
    assert actual.status_code == 200
    assert actual.json()["id"] == sesion["id"]


def test_dos_usuarios_pueden_tener_sesion_en_curso_a_la_vez(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    sesion_ana = iniciar(client, ana)
    sesion_beto = iniciar(client, beto)
    assert sesion_ana["id"] != sesion_beto["id"]
    actual_beto = client.get(f"{URL}/actual", headers=beto.headers).json()
    assert actual_beto["id"] == sesion_beto["id"]
    detenido = client.post(f"{URL}/detener", headers=beto.headers)
    assert detenido.status_code == 200
    assert client.get(f"{URL}/actual", headers=ana.headers).status_code == 200


def test_categoria_inexistente_o_propia_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    secreta = categoria_propia(client, ana)
    for categoria in (str(uuid4()), secreta):
        respuesta = client.post(
            f"{URL}/iniciar", json={"categoria_id": categoria}, headers=beto.headers
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "referencia_invalida"
    assert client.get(f"{URL}/actual", headers=beto.headers).status_code == 404


def test_actividad_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    respuesta = client.post(
        f"{URL}/iniciar",
        json={
            "categoria_id": categoria_id(client, beto),
            "actividad_id": actividad,
        },
        headers=beto.headers,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "referencia_invalida"


def test_temporizador_sin_token_responde_401(client: TestClient) -> None:
    assert client.get(f"{URL}/actual").status_code == 401
    assert client.post(f"{URL}/detener").status_code == 401
