from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from tests.doble_extractor import (
    ExtractorFalso,
    actividad,
    meta,
    registro,
    usar_extractor,
)
from tests.helpers import Sesion, crear_sesion

ZONA = ZoneInfo("America/Mexico_City")
BASE = "/api/v1/capturas"


def _consultar(
    consulta: str, parametros: tuple[object, ...] = ()
) -> list[tuple[Any, ...]]:
    with psycopg.connect(Settings().database_url, autocommit=True) as conn:
        return conn.execute(consulta, parametros).fetchall()


def _capturar(
    client: TestClient, sesion: Sesion, extractor: ExtractorFalso, texto: str = "hola"
) -> dict[str, Any]:
    usar_extractor(client, extractor)
    respuesta = client.post(BASE, json={"texto": texto}, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


def _materia(client: TestClient, sesion: Sesion, nombre: str) -> str:
    respuesta = client.post(
        "/api/v1/materias",
        json={"nombre": nombre, "periodo": "2026-3"},
        headers=sesion.headers,
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


def _viernes_proximo() -> str:
    hoy = datetime.now(ZONA).date()
    salto = (4 - hoy.weekday()) % 7 or 7
    return f"{hoy + timedelta(days=salto)}T23:59:00-06:00"


def test_texto_de_actividad_termina_en_una_actividad_confirmada(
    client: TestClient, ana: Sesion
) -> None:
    materia_id = _materia(client, ana, "Redes de Computadoras")
    texto = "entregar el reporte de redes el viernes"
    captura = _capturar(
        client,
        ana,
        ExtractorFalso(
            actividad(materia="redes de computadoras", fecha_texto="el viernes")
        ),
        texto,
    )
    assert captura["estado"] == "pendiente"
    assert captura["entidad_tipo"] == "actividad"
    assert captura["mensaje"] == texto
    assert captura["modelo"] == "modelo-falso"
    assert captura["confianza"] == 0.9
    assert captura["pendientes"] == []
    assert captura["resultado_id"] is None
    assert captura["campos"]["materia_id"] == materia_id
    assert captura["campos"]["vence_en"] == _viernes_proximo()

    pendiente = client.get(f"{BASE}/{captura['id']}", headers=ana.headers)
    assert pendiente.status_code == 200
    assert pendiente.json()["estado"] == "pendiente"
    assert client.get("/api/v1/actividades", headers=ana.headers).json() == []

    confirmada = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["estado"] == "aceptada"
    actividad_id = confirmada.json()["resultado_id"]

    creada = client.get(f"/api/v1/actividades/{actividad_id}", headers=ana.headers)
    assert creada.status_code == 200
    assert creada.json()["titulo"] == "Entregar reporte de redes"
    assert creada.json()["materia_id"] == materia_id

    procedencia = _consultar(
        "select e.estado, e.actividad_id::text, m.texto from extraccion e "
        "join mensaje_origen m on m.id = e.mensaje_origen_id where e.id = %s",
        (captura["id"],),
    )
    assert procedencia == [("aceptada", actividad_id, texto)]


def test_confirmar_dos_veces_es_idempotente(client: TestClient, ana: Sesion) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad()))
    primera = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    segunda = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["resultado_id"] == segunda.json()["resultado_id"]
    assert len(client.get("/api/v1/actividades", headers=ana.headers).json()) == 1


def test_materia_con_otro_acento_se_resuelve(client: TestClient, ana: Sesion) -> None:
    materia_id = _materia(client, ana, "Cálculo Diferencial")
    captura = _capturar(
        client, ana, ExtractorFalso(actividad(materia="CALCULO diferencial"))
    )
    assert captura["campos"]["materia_id"] == materia_id
    assert captura["pendientes"] == []


def test_materia_inexistente_queda_vacia_y_marcada(
    client: TestClient, ana: Sesion
) -> None:
    _materia(client, ana, "Redes")
    captura = _capturar(client, ana, ExtractorFalso(actividad(materia="Alquimia")))
    assert captura["campos"]["materia_id"] is None
    assert captura["pendientes"] == ["materia_id"]
    confirmada = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert confirmada.status_code == 200
    creada = client.get(
        f"/api/v1/actividades/{confirmada.json()['resultado_id']}", headers=ana.headers
    )
    assert creada.json()["materia_id"] is None


def test_el_extractor_solo_recibe_nombres_del_usuario(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    _materia(client, ana, "Materia de Ana")
    _materia(client, beto, "Materia de Beto")
    extractor = ExtractorFalso(actividad())
    _capturar(client, ana, extractor)
    _, materias, categorias = extractor.llamadas[0]
    assert materias == ["Materia de Ana"]
    assert "Tarea" in categorias


def test_fecha_pasada_no_se_acepta_como_vencimiento(
    client: TestClient, ana: Sesion
) -> None:
    captura = _capturar(
        client, ana, ExtractorFalso(actividad(fecha_texto="25/11/2020"))
    )
    assert captura["campos"]["vence_en"] is None
    assert captura["pendientes"] == ["vence_en"]


def test_categoria_inexistente_exige_corregir(client: TestClient, ana: Sesion) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad(categoria="Inventada")))
    assert captura["pendientes"] == ["categoria_id"]
    rechazo = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert rechazo.status_code == 422
    assert rechazo.json()["codigo"] == "captura_incompleta"
    assert "categoria_id" in rechazo.json()["detalle"]
    assert client.get("/api/v1/actividades", headers=ana.headers).json() == []
    assert (
        client.get(f"{BASE}/{captura['id']}", headers=ana.headers).json()["estado"]
        == "pendiente"
    )


def test_corregir_guarda_los_campos_cambiados(client: TestClient, ana: Sesion) -> None:
    categorias = client.get("/api/v1/categorias", headers=ana.headers).json()
    examen = next(c["id"] for c in categorias if c["nombre"] == "Examen")
    captura = _capturar(client, ana, ExtractorFalso(actividad(categoria="Inventada")))
    respuesta = client.post(
        f"{BASE}/{captura['id']}/corregir",
        json={"campos": {"categoria_id": examen, "prioridad": 5, "titulo": "Examen"}},
        headers=ana.headers,
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "corregida"
    creada = client.get(
        f"/api/v1/actividades/{respuesta.json()['resultado_id']}", headers=ana.headers
    ).json()
    assert creada["categoria_id"] == examen
    assert creada["prioridad"] == 5
    assert creada["titulo"] == "Examen"

    correcciones = _consultar(
        "select campo, valor_propuesto::text, valor_final::text "
        "from correccion_campo where extraccion_id = %s order by campo",
        (captura["id"],),
    )
    assert correcciones == [
        ("categoria_id", "null", f'"{examen}"'),
        ("prioridad", "3", "5"),
        ("titulo", '"Entregar reporte de redes"', '"Examen"'),
    ]


def test_corregir_sin_cambios_reales_cuenta_como_aceptada(
    client: TestClient, ana: Sesion
) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad(prioridad=2)))
    respuesta = client.post(
        f"{BASE}/{captura['id']}/corregir",
        json={"campos": {"prioridad": 2}},
        headers=ana.headers,
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "aceptada"
    assert (
        _consultar(
            "select 1 from correccion_campo where extraccion_id = %s", (captura["id"],)
        )
        == []
    )


def test_corregir_valida_campos_y_valores(client: TestClient, ana: Sesion) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad()))
    desconocido = client.post(
        f"{BASE}/{captura['id']}/corregir",
        json={"campos": {"inventado": 1}},
        headers=ana.headers,
    )
    assert desconocido.status_code == 422
    assert desconocido.json()["codigo"] == "validacion"
    fuera_de_dominio = client.post(
        f"{BASE}/{captura['id']}/corregir",
        json={"campos": {"prioridad": 9}},
        headers=ana.headers,
    )
    assert fuera_de_dominio.status_code == 422
    assert fuera_de_dominio.json()["codigo"] == "captura_incompleta"
    vacio = client.post(
        f"{BASE}/{captura['id']}/corregir", json={"campos": {}}, headers=ana.headers
    )
    assert vacio.status_code == 422


def test_corregir_una_captura_cerrada_es_conflicto(
    client: TestClient, ana: Sesion
) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad()))
    client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    respuesta = client.post(
        f"{BASE}/{captura['id']}/corregir",
        json={"campos": {"prioridad": 1}},
        headers=ana.headers,
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "captura_cerrada"


def test_descartar_no_inserta_y_es_idempotente(client: TestClient, ana: Sesion) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad()))
    primera = client.post(f"{BASE}/{captura['id']}/descartar", headers=ana.headers)
    segunda = client.post(f"{BASE}/{captura['id']}/descartar", headers=ana.headers)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["estado"] == "descartada"
    assert client.get("/api/v1/actividades", headers=ana.headers).json() == []

    confirmar = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert confirmar.status_code == 409
    assert confirmar.json()["codigo"] == "captura_descartada"
    corregir = client.post(
        f"{BASE}/{captura['id']}/corregir",
        json={"campos": {"prioridad": 1}},
        headers=ana.headers,
    )
    assert corregir.status_code == 409


def test_descartar_una_captura_confirmada_es_conflicto(
    client: TestClient, ana: Sesion
) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad()))
    client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    respuesta = client.post(f"{BASE}/{captura['id']}/descartar", headers=ana.headers)
    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "captura_cerrada"


def test_registro_de_tiempo_sin_fecha_termina_ahora(
    client: TestClient, ana: Sesion
) -> None:
    captura = _capturar(client, ana, ExtractorFalso(registro(duracion_min=90)))
    assert captura["entidad_tipo"] == "registro_tiempo"
    assert captura["pendientes"] == []
    confirmada = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert confirmada.status_code == 200, confirmada.text
    creado = client.get(
        f"/api/v1/registros-tiempo/{confirmada.json()['resultado_id']}",
        headers=ana.headers,
    ).json()
    assert creado["duracion_s"] == 5400
    assert creado["origen"] == "manual"


def test_registro_de_tiempo_sin_hora_no_inventa_el_inicio(
    client: TestClient, ana: Sesion
) -> None:
    captura = _capturar(
        client, ana, ExtractorFalso(registro(fecha_texto="ayer", duracion_min=60))
    )
    assert captura["pendientes"] == ["inicio", "fin"]
    rechazo = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert rechazo.status_code == 422
    assert rechazo.json()["codigo"] == "captura_incompleta"


def test_meta_en_horas_se_guarda_en_minutos(client: TestClient, ana: Sesion) -> None:
    captura = _capturar(client, ana, ExtractorFalso(meta(objetivo=2, unidad="horas")))
    assert captura["entidad_tipo"] == "meta"
    assert captura["campos"]["objetivo"] == 120
    confirmada = client.post(f"{BASE}/{captura['id']}/confirmar", headers=ana.headers)
    assert confirmada.status_code == 200, confirmada.text
    creada = client.get(
        f"/api/v1/metas/{confirmada.json()['resultado_id']}", headers=ana.headers
    ).json()
    assert creada["objetivo"] == 120
    assert creada["tipo"] == "tiempo_acumulado"


def test_fallo_del_proveedor_responde_503_y_no_guarda_nada(
    client: TestClient, ana: Sesion
) -> None:
    usar_extractor(client, ExtractorFalso(None))
    respuesta = client.post(BASE, json={"texto": "tarea"}, headers=ana.headers)
    assert respuesta.status_code == 503
    assert respuesta.json()["codigo"] == "extraccion_no_disponible"
    assert (
        _consultar("select 1 from mensaje_origen where usuario_id = %s", (ana.id,))
        == []
    )
    assert _consultar("select 1 from extraccion where usuario_id = %s", (ana.id,)) == []


def test_sin_llm_configurado_responde_503(
    client: TestClient, ana: Sesion, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    respuesta = client.post(BASE, json={"texto": "tarea"}, headers=ana.headers)
    assert respuesta.status_code == 503
    assert respuesta.json()["codigo"] == "extraccion_no_disponible"


def test_validaciones_de_entrada(client: TestClient, ana: Sesion) -> None:
    usar_extractor(client, ExtractorFalso(actividad()))
    vacio = client.post(BASE, json={"texto": "   "}, headers=ana.headers)
    assert vacio.status_code == 422
    largo = client.post(BASE, json={"texto": "x" * 1001}, headers=ana.headers)
    assert largo.status_code == 422
    extra = client.post(BASE, json={"texto": "a", "canal": "x"}, headers=ana.headers)
    assert extra.status_code == 422
    sin_token = client.post(BASE, json={"texto": "a"})
    assert sin_token.status_code == 401


def test_otro_usuario_no_ve_ni_modifica_la_captura(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    captura = _capturar(client, ana, ExtractorFalso(actividad()))
    ruta = f"{BASE}/{captura['id']}"
    assert client.get(ruta, headers=beto.headers).status_code == 404
    assert client.post(f"{ruta}/confirmar", headers=beto.headers).status_code == 404
    assert client.post(f"{ruta}/descartar", headers=beto.headers).status_code == 404
    assert (
        client.post(
            f"{ruta}/corregir", json={"campos": {"prioridad": 1}}, headers=beto.headers
        ).status_code
        == 404
    )
    assert client.get(ruta, headers=ana.headers).json()["estado"] == "pendiente"
    assert client.get(f"{BASE}/no-es-un-uuid", headers=ana.headers).status_code == 422


def test_metricas_de_aceptacion_por_tipo(client: TestClient) -> None:
    usuaria = crear_sesion(client)
    vacias = client.get(f"{BASE}/metricas", headers=usuaria.headers).json()
    assert [m["entidad_tipo"] for m in vacias] == [
        "actividad",
        "meta",
        "registro_tiempo",
    ]
    assert all(
        m["total"] == 0 and m["porcentaje_sin_correccion"] is None for m in vacias
    )

    limpia = _capturar(client, usuaria, ExtractorFalso(actividad(titulo="Uno")))
    client.post(f"{BASE}/{limpia['id']}/confirmar", headers=usuaria.headers)
    corregida = _capturar(client, usuaria, ExtractorFalso(actividad(titulo="Dos")))
    client.post(
        f"{BASE}/{corregida['id']}/corregir",
        json={"campos": {"titulo": "Dos corregido", "prioridad": 4}},
        headers=usuaria.headers,
    )
    descartada = _capturar(client, usuaria, ExtractorFalso(actividad(titulo="Tres")))
    client.post(f"{BASE}/{descartada['id']}/descartar", headers=usuaria.headers)
    _capturar(client, usuaria, ExtractorFalso(actividad(titulo="Cuatro")))

    metricas = {
        m["entidad_tipo"]: m
        for m in client.get(f"{BASE}/metricas", headers=usuaria.headers).json()
    }
    act = metricas["actividad"]
    assert (act["total"], act["pendientes"], act["aceptadas"]) == (4, 1, 1)
    assert (act["corregidas"], act["descartadas"]) == (1, 1)
    assert act["porcentaje_sin_correccion"] == pytest.approx(33.3)
    assert act["promedio_campos_corregidos"] == pytest.approx(1.0)
    assert metricas["meta"]["total"] == 0
