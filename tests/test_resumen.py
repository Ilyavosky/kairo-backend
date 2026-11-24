import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.resumen import (
    RedaccionNoDisponible,
    RedactorGroq,
    texto_verificado,
)
from tests.doble_redactor import RedactorFalso, usar_redactor
from tests.helpers import Sesion
from tests.test_reportes import BASE, sembrar

META = {
    "categoria_id": None,
    "tipo": "tiempo_acumulado",
    "periodo": "mes",
    "objetivo": 100,
}


def preparar(client: TestClient, sesion: Sesion) -> None:
    ids = sembrar(client, sesion)
    client.post(
        "/api/v1/metas",
        json={**META, "categoria_id": ids["estudio"]},
        headers=sesion.headers,
    )


def pedir(client: TestClient, sesion: Sesion) -> dict[str, Any]:
    respuesta = client.get(f"{BASE}/resumen", headers=sesion.headers)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


def test_devuelve_el_texto_cuando_solo_usa_cifras_reales(
    client: TestClient, ana: Sesion
) -> None:
    preparar(client, ana)
    redactor = RedactorFalso("Tu meta del mes es de 100 minutos.")
    usar_redactor(client, redactor)
    resumen = pedir(client, ana)
    assert resumen["texto"] == "Tu meta del mes es de 100 minutos."
    assert resumen["modelo"] == "redactor-falso"
    assert resumen["motivo_sin_texto"] is None
    assert resumen["cifras"]["metas"][0]["objetivo"] == 100


def test_descarta_un_texto_con_numeros_inventados(
    client: TestClient, ana: Sesion
) -> None:
    preparar(client, ana)
    usar_redactor(client, RedactorFalso("Cumpliste 777 minutos de estudio."))
    resumen = pedir(client, ana)
    assert resumen["texto"] is None
    assert resumen["modelo"] is None
    assert resumen["motivo_sin_texto"] == "texto_no_verificado"
    assert resumen["cifras"]["metas"][0]["objetivo"] == 100


def test_si_el_redactor_falla_salen_las_cifras_sin_texto(
    client: TestClient, ana: Sesion
) -> None:
    preparar(client, ana)
    usar_redactor(client, RedactorFalso(falla="estado 500"))
    resumen = pedir(client, ana)
    assert resumen["texto"] is None
    assert resumen["motivo_sin_texto"] == "estado 500"
    assert len(resumen["cifras"]["agenda"]) == 2


def test_sin_llave_del_proveedor_sale_sin_texto(
    client: TestClient, ana: Sesion, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    resumen = pedir(client, ana)
    assert resumen["texto"] is None
    assert resumen["motivo_sin_texto"] == "sin_configurar"


def test_el_redactor_no_recibe_identificadores_ni_titulos_largos(
    client: TestClient, ana: Sesion
) -> None:
    ids = sembrar(client, ana)
    client.patch(
        f"/api/v1/actividades/{ids['actividad']}",
        json={"titulo": "x" * 150},
        headers=ana.headers,
    )
    redactor = RedactorFalso("Sin novedades.")
    usar_redactor(client, redactor)
    pedir(client, ana)
    entrada = redactor.recibidas[0]
    texto = json.dumps(entrada)
    for identificador in (ids["actividad"], ids["materia"], ids["estudio"]):
        assert identificador not in texto
    titulo = next(a["titulo"] for a in entrada["agenda"] if a["tipo"] == "actividad")
    assert len(titulo) == 80


def test_el_resumen_es_solo_del_usuario(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    preparar(client, ana)
    redactor = RedactorFalso("Sin novedades.")
    usar_redactor(client, redactor)
    resumen = pedir(client, beto)
    assert resumen["cifras"]["agenda"] == []
    assert redactor.recibidas[0]["agenda"] == []


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Llevas 30 minutos.", True),
        ("Llevas 30,5 minutos.", True),
        ("Llevas 30 minutos, el 75 % de la meta.", False),
        ("Sin cifras en este texto.", True),
        ("Son 31 minutos.", False),
    ],
)
def test_texto_verificado(texto: str, esperado: bool) -> None:
    cifras = {"metas": [{"progreso": 30.5, "objetivo": 100}]}
    assert texto_verificado(texto, cifras) is esperado


def cliente_groq(manejador: httpx.MockTransport) -> RedactorGroq:
    return RedactorGroq(
        api_key="llave-de-prueba",
        modelo="modelo",
        base_url="https://proveedor.test/v1",
        transport=manejador,
    )


async def test_groq_devuelve_el_texto_del_esquema() -> None:
    vistas: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        vistas.append(peticion)
        contenido = json.dumps({"texto": "  Todo en orden.  "})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": contenido}}]}
        )

    redactor = cliente_groq(httpx.MockTransport(responder))
    assert await redactor.redactar({"agenda": []}) == "Todo en orden."
    assert vistas[0].headers["authorization"] == "Bearer llave-de-prueba"
    cuerpo = json.loads(vistas[0].content)
    assert cuerpo["response_format"]["json_schema"]["strict"] is True


async def test_groq_reintenta_una_vez_y_luego_se_rinde() -> None:
    llamadas = 0

    def responder(_: httpx.Request) -> httpx.Response:
        nonlocal llamadas
        llamadas += 1
        return httpx.Response(500)

    redactor = cliente_groq(httpx.MockTransport(responder))
    with pytest.raises(RedaccionNoDisponible):
        await redactor.redactar({})
    assert llamadas == 2


async def test_groq_rechaza_una_respuesta_que_no_cumple_el_esquema() -> None:
    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "no es json"}}]}
        )

    redactor = cliente_groq(httpx.MockTransport(responder))
    with pytest.raises(RedaccionNoDisponible):
        await redactor.redactar({})
