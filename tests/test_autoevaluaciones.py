from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.helpers import Sesion

URL = "/api/v1/autoevaluaciones"


def lunes_pasado() -> date:
    hoy = date.today()
    return hoy - timedelta(days=hoy.weekday() + 7)


def cuerpo(
    animo: int = 4, satisfaccion: int = 3, nota: str | None = None
) -> dict[str, object]:
    return {"estado_animo": animo, "satisfaccion": satisfaccion, "nota": nota}


def test_guarda_y_lee_la_autoevaluacion_de_una_semana(
    client: TestClient, ana: Sesion
) -> None:
    semana = lunes_pasado()
    respuesta = client.put(
        f"{URL}/{semana}", json=cuerpo(nota="buena"), headers=ana.headers
    )
    assert respuesta.status_code == 200, respuesta.text
    leida = client.get(f"{URL}/{semana}", headers=ana.headers).json()
    assert leida["semana_desde"] == semana.isoformat()
    assert leida["estado_animo"] == 4 and leida["nota"] == "buena"


def test_guardar_dos_veces_actualiza_sin_duplicar(
    client: TestClient, ana: Sesion
) -> None:
    semana = lunes_pasado()
    client.put(f"{URL}/{semana}", json=cuerpo(2, 2), headers=ana.headers)
    segunda = client.put(f"{URL}/{semana}", json=cuerpo(5, 4), headers=ana.headers)
    assert segunda.status_code == 200
    assert segunda.json()["estado_animo"] == 5
    assert len(client.get(URL, headers=ana.headers).json()) == 1


def test_la_semana_debe_ser_un_lunes(client: TestClient, ana: Sesion) -> None:
    martes = lunes_pasado() + timedelta(days=1)
    respuesta = client.put(f"{URL}/{martes}", json=cuerpo(), headers=ana.headers)
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "semana_invalida"


def test_no_se_evalua_una_semana_futura(client: TestClient, ana: Sesion) -> None:
    futura = lunes_pasado() + timedelta(days=28)
    respuesta = client.put(f"{URL}/{futura}", json=cuerpo(), headers=ana.headers)
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "semana_futura"


def test_valida_la_escala(client: TestClient, ana: Sesion) -> None:
    semana = lunes_pasado()
    for animo, satisfaccion in ((0, 3), (6, 3), (3, 0), (3, 6)):
        respuesta = client.put(
            f"{URL}/{semana}", json=cuerpo(animo, satisfaccion), headers=ana.headers
        )
        assert respuesta.status_code == 422


def test_semana_sin_registro_devuelve_404(client: TestClient, ana: Sesion) -> None:
    assert client.get(f"{URL}/{lunes_pasado()}", headers=ana.headers).status_code == 404


def test_aislamiento_entre_usuarios(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    semana = lunes_pasado()
    client.put(f"{URL}/{semana}", json=cuerpo(), headers=ana.headers)
    assert client.get(f"{URL}/{semana}", headers=beto.headers).status_code == 404
    assert client.get(URL, headers=beto.headers).json() == []
    client.put(f"{URL}/{semana}", json=cuerpo(1, 1), headers=beto.headers)
    assert (
        client.get(f"{URL}/{semana}", headers=ana.headers).json()["estado_animo"] == 4
    )
