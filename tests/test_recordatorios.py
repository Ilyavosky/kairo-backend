from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.helpers import Sesion, crear_actividad

URL = "/api/v1/recordatorios"


def en(horas: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=horas)).isoformat()


def crear(client: TestClient, sesion: Sesion, **cuerpo: object) -> dict[str, object]:
    respuesta = client.post(URL, json=cuerpo, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def test_crea_un_recordatorio_pendiente_para_una_actividad(
    client: TestClient, ana: Sesion
) -> None:
    actividad = crear_actividad(client, ana)
    recordatorio = crear(client, ana, actividad_id=actividad, momento=en(2))
    assert recordatorio["estado_envio"] == "pendiente"
    assert recordatorio["intentos"] == 0
    assert recordatorio["enviado_en"] is None
    listado = client.get(URL, headers=ana.headers).json()
    assert [r["id"] for r in listado] == [recordatorio["id"]]


def test_exige_exactamente_un_objetivo(client: TestClient, ana: Sesion) -> None:
    actividad = crear_actividad(client, ana)
    ninguno = client.post(URL, json={"momento": en(1)}, headers=ana.headers)
    assert ninguno.status_code == 422
    dos = client.post(
        URL,
        json={"actividad_id": actividad, "meta_id": str(uuid4()), "momento": en(1)},
        headers=ana.headers,
    )
    assert dos.status_code == 422


def test_rechaza_momento_sin_zona_horaria(client: TestClient, ana: Sesion) -> None:
    actividad = crear_actividad(client, ana)
    respuesta = client.post(
        URL,
        json={"actividad_id": actividad, "momento": "2026-12-01T10:00:00"},
        headers=ana.headers,
    )
    assert respuesta.status_code == 422


def test_no_permite_apuntar_a_la_actividad_de_otro(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    ajena = crear_actividad(client, beto)
    respuesta = client.post(
        URL, json={"actividad_id": ajena, "momento": en(1)}, headers=ana.headers
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "referencia_invalida"


def test_aislamiento_entre_usuarios(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    recordatorio = crear(
        client, ana, actividad_id=crear_actividad(client, ana), momento=en(1)
    )
    assert client.get(URL, headers=beto.headers).json() == []
    assert (
        client.get(f"{URL}/{recordatorio['id']}", headers=beto.headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"{URL}/{recordatorio['id']}",
            json={"estado_envio": "cancelado"},
            headers=beto.headers,
        ).status_code
        == 404
    )


def test_cancela_y_reprograma_mientras_este_pendiente(
    client: TestClient, ana: Sesion
) -> None:
    recordatorio = crear(
        client, ana, actividad_id=crear_actividad(client, ana), momento=en(1)
    )
    ruta = f"{URL}/{recordatorio['id']}"
    nuevo = en(5)
    reprogramado = client.patch(ruta, json={"momento": nuevo}, headers=ana.headers)
    assert reprogramado.status_code == 200
    assert datetime.fromisoformat(
        reprogramado.json()["momento"]
    ) == datetime.fromisoformat(nuevo)
    cancelado = client.patch(
        ruta, json={"estado_envio": "cancelado"}, headers=ana.headers
    )
    assert cancelado.json()["estado_envio"] == "cancelado"
    otra_vez = client.patch(ruta, json={"momento": en(9)}, headers=ana.headers)
    assert otra_vez.status_code == 409
    assert otra_vez.json()["codigo"] == "recordatorio_cerrado"


def test_el_usuario_no_puede_marcar_un_recordatorio_como_enviado(
    client: TestClient, ana: Sesion
) -> None:
    recordatorio = crear(
        client, ana, actividad_id=crear_actividad(client, ana), momento=en(1)
    )
    respuesta = client.patch(
        f"{URL}/{recordatorio['id']}",
        json={"estado_envio": "enviado"},
        headers=ana.headers,
    )
    assert respuesta.status_code == 422


def test_filtra_por_estado(client: TestClient, ana: Sesion) -> None:
    actividad = crear_actividad(client, ana)
    uno = crear(client, ana, actividad_id=actividad, momento=en(1))
    crear(client, ana, actividad_id=actividad, momento=en(2))
    client.patch(
        f"{URL}/{uno['id']}", json={"estado_envio": "cancelado"}, headers=ana.headers
    )
    cancelados = client.get(URL, params={"estado": "cancelado"}, headers=ana.headers)
    assert [r["id"] for r in cancelados.json()] == [uno["id"]]
