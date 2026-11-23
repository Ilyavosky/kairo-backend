import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.services.extraccion import (
    ExtraccionNoDisponible,
    ExtractorGroq,
    ExtractorNoConfigurado,
    PropuestaActividad,
    RespuestaLLM,
    crear_extractor,
    esquema_estricto,
)

CONTENIDO_VALIDO = json.dumps(
    {
        "confianza": 0.93,
        "propuesta": {
            "entidad_tipo": "actividad",
            "titulo": "Entregar reporte de redes",
            "descripcion": None,
            "materia": "Redes",
            "categoria": "Tarea",
            "fecha_texto": "el viernes",
            "hora_texto": None,
            "prioridad": None,
            "modalidad": None,
        },
    }
)


def _ok(contenido: str = CONTENIDO_VALIDO) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": contenido}}]})


def _extractor(
    *respuestas: httpx.Response | Exception,
) -> tuple[ExtractorGroq, list[Any]]:
    cola = list(respuestas)
    vistas: list[httpx.Request] = []

    def manejar(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        siguiente = cola.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    extractor = ExtractorGroq(
        api_key="clave-de-prueba",
        modelo="modelo-x",
        base_url="https://llm.prueba/v1",
        transport=httpx.MockTransport(manejar),
    )
    return extractor, vistas


def _objetos(nodo: Any) -> list[dict[str, Any]]:
    if isinstance(nodo, list):
        return [o for n in nodo for o in _objetos(n)]
    if not isinstance(nodo, dict):
        return []
    encontrados = [nodo] if "properties" in nodo else []
    for clave, valor in nodo.items():
        if clave == "properties":
            encontrados += [o for v in valor.values() for o in _objetos(v)]
        else:
            encontrados += _objetos(valor)
    return encontrados


def test_esquema_estricto_cumple_las_reglas_del_proveedor() -> None:
    esquema = esquema_estricto()
    texto = json.dumps(esquema)
    for prohibido in ("oneOf", "const", "discriminator", '"default"', '"title"'):
        assert prohibido not in texto
    objetos = _objetos(esquema)
    assert len(objetos) >= 4
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert objeto["required"] == list(objeto["properties"])
    variantes = esquema["properties"]["propuesta"]["anyOf"]
    assert len(variantes) == 3


def test_respuesta_se_valida_con_la_union_discriminada() -> None:
    respuesta = RespuestaLLM.model_validate_json(CONTENIDO_VALIDO)
    assert isinstance(respuesta.propuesta, PropuestaActividad)
    assert respuesta.propuesta.materia == "Redes"
    with pytest.raises(ValueError, match="entidad_tipo"):
        RespuestaLLM.model_validate(
            {"confianza": 1, "propuesta": {"entidad_tipo": "x"}}
        )


async def test_extrae_con_esquema_estricto_y_clave() -> None:
    extractor, vistas = _extractor(_ok())
    respuesta = await extractor.extraer(
        "entregar el reporte de redes el viernes", ["Redes"], ["Tarea"]
    )
    assert respuesta.confianza == 0.93
    assert len(vistas) == 1
    peticion = vistas[0]
    assert str(peticion.url) == "https://llm.prueba/v1/chat/completions"
    assert peticion.headers["authorization"] == "Bearer clave-de-prueba"
    cuerpo = json.loads(peticion.content)
    assert cuerpo["model"] == "modelo-x"
    formato = cuerpo["response_format"]
    assert formato["type"] == "json_schema"
    assert formato["json_schema"]["strict"] is True
    usuario = cuerpo["messages"][1]["content"]
    assert "Materias: Redes" in usuario
    assert "Categorias: Tarea" in usuario
    assert "entregar el reporte de redes el viernes" in usuario


@pytest.mark.parametrize(
    "fallo",
    [
        httpx.Response(500),
        httpx.Response(429),
        httpx.ReadTimeout("lento"),
        httpx.ConnectError("sin red"),
        _ok("esto no es json"),
        _ok('{"confianza": 1, "propuesta": {"entidad_tipo": "nada"}}'),
        httpx.Response(200, json={"sin": "choices"}),
    ],
)
async def test_un_fallo_transitorio_se_reintenta_una_vez(
    fallo: httpx.Response | Exception,
) -> None:
    extractor, vistas = _extractor(fallo, _ok())
    respuesta = await extractor.extraer("texto", [], [])
    assert respuesta.confianza == 0.93
    assert len(vistas) == 2


async def test_dos_fallos_seguidos_agotan_el_reintento() -> None:
    extractor, vistas = _extractor(httpx.Response(503), httpx.ReadTimeout("lento"))
    with pytest.raises(ExtraccionNoDisponible):
        await extractor.extraer("texto", [], [])
    assert len(vistas) == 2


async def test_un_error_de_cliente_no_se_reintenta() -> None:
    extractor, vistas = _extractor(httpx.Response(401), _ok())
    with pytest.raises(ExtraccionNoDisponible):
        await extractor.extraer("texto", [], [])
    assert len(vistas) == 1


async def test_sin_clave_configurada_no_hay_extraccion() -> None:
    extractor = crear_extractor(Settings(llm_api_key=""))
    assert isinstance(extractor, ExtractorNoConfigurado)
    with pytest.raises(ExtraccionNoDisponible):
        await extractor.extraer("texto", [], [])


def test_con_clave_se_usa_el_proveedor_y_el_modelo_por_defecto() -> None:
    extractor = crear_extractor(Settings(llm_api_key="abc", llm_model=" "))
    assert isinstance(extractor, ExtractorGroq)
    assert extractor.modelo == "openai/gpt-oss-20b"
