from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.doble_extractor import ExtractorFalso, actividad, usar_extractor
from tests.helpers import Sesion, categoria_id

BASE = "/api/v1/reportes"
RUTAS = ["agenda", "carga-semanal", "metas", "pipeline", "carga-vs-descanso", "resumen"]


def en(**delta: float) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


def obtener(client: TestClient, sesion: Sesion, ruta: str, **params: Any) -> Any:
    respuesta = client.get(f"{BASE}/{ruta}", params=params, headers=sesion.headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def sembrar(client: TestClient, sesion: Sesion) -> dict[str, str]:
    materia = client.post(
        "/api/v1/materias",
        json={"nombre": "Redes", "periodo": "2026-3"},
        headers=sesion.headers,
    ).json()["id"]
    tarea = client.post(
        "/api/v1/actividades",
        json={
            "titulo": "Reporte de redes",
            "categoria_id": categoria_id(client, sesion, "Tarea"),
            "materia_id": materia,
            "vence_en": en(days=2),
        },
        headers=sesion.headers,
    ).json()["id"]
    client.post(
        "/api/v1/eventos",
        json={"titulo": "Clase de redes", "inicio": en(hours=20), "fin": en(hours=21)},
        headers=sesion.headers,
    )
    estudio = categoria_id(client, sesion, "Estudio")
    cuerpo = {
        "categoria_id": estudio,
        "actividad_id": tarea,
        "inicio": en(minutes=-12),
        "fin": en(minutes=-2),
    }
    assert (
        client.post("/api/v1/registros-tiempo", json=cuerpo, headers=sesion.headers)
    ).status_code == 201
    return {"materia": materia, "actividad": tarea, "estudio": estudio}


@pytest.mark.parametrize("ruta", RUTAS)
def test_los_reportes_exigen_sesion(client: TestClient, ruta: str) -> None:
    assert client.get(f"{BASE}/{ruta}").status_code == 401


def test_agenda_trae_actividades_y_eventos_en_orden(
    client: TestClient, ana: Sesion
) -> None:
    sembrar(client, ana)
    agenda = obtener(client, ana, "agenda")
    assert [a["tipo"] for a in agenda] == ["evento", "actividad"]
    assert agenda[1]["titulo"] == "Reporte de redes"
    assert agenda[1]["materia"] == "Redes"
    assert agenda[1]["categoria"] == "Tarea"
    solo_hoy = obtener(client, ana, "agenda", dias=1)
    assert [a["tipo"] for a in solo_hoy] == ["evento"]


def test_agenda_excluye_las_actividades_cerradas(
    client: TestClient, ana: Sesion
) -> None:
    ids = sembrar(client, ana)
    client.patch(
        f"/api/v1/actividades/{ids['actividad']}",
        json={"estado": "completada"},
        headers=ana.headers,
    )
    assert [a["tipo"] for a in obtener(client, ana, "agenda")] == ["evento"]


def test_carga_semanal_suma_vencimientos_y_minutos_por_materia(
    client: TestClient, ana: Sesion
) -> None:
    sembrar(client, ana)
    filas = obtener(client, ana, "carga-semanal")
    redes = [f for f in filas if f["materia"] == "Redes"]
    assert sum(f["actividades_con_vencimiento"] for f in redes) == 1
    assert sum(f["actividades_pendientes"] for f in redes) == 1
    assert sum(f["minutos_registrados"] for f in redes) == pytest.approx(10)
    assert all(datetime.fromisoformat(f["semana_desde"]).weekday() == 0 for f in redes)


def test_metas_muestra_el_progreso_del_periodo(client: TestClient, ana: Sesion) -> None:
    ids = sembrar(client, ana)
    client.post(
        "/api/v1/metas",
        json={
            "categoria_id": ids["estudio"],
            "tipo": "tiempo_acumulado",
            "periodo": "mes",
            "objetivo": 100,
        },
        headers=ana.headers,
    )
    metas = obtener(client, ana, "metas")
    assert len(metas) == 1
    assert metas[0]["categoria"] == "Estudio"
    assert metas[0]["progreso"] == pytest.approx(10)
    assert metas[0]["porcentaje"] == pytest.approx(10.0)
    assert metas[0]["cumplida"] is False


def test_pipeline_siempre_trae_los_tres_tipos(client: TestClient, ana: Sesion) -> None:
    filas = obtener(client, ana, "pipeline")
    assert [f["entidad_tipo"] for f in filas] == [
        "actividad",
        "meta",
        "registro_tiempo",
    ]
    assert all(
        f["total"] == 0 and f["porcentaje_sin_correccion"] is None for f in filas
    )


def test_pipeline_refleja_una_captura_aceptada(client: TestClient, ana: Sesion) -> None:
    usar_extractor(client, ExtractorFalso(actividad("Entregar reporte")))
    captura = client.post(
        "/api/v1/capturas", json={"texto": "entregar reporte"}, headers=ana.headers
    ).json()
    client.post(f"/api/v1/capturas/{captura['id']}/confirmar", headers=ana.headers)
    fila = next(
        f for f in obtener(client, ana, "pipeline") if f["entidad_tipo"] == "actividad"
    )
    assert fila["aceptadas"] == 1
    assert fila["porcentaje_sin_correccion"] == pytest.approx(100.0)


def test_carga_vs_descanso_separa_academico_sueno_y_ejercicio(
    client: TestClient, ana: Sesion
) -> None:
    sembrar(client, ana)
    for nombre, minutos in (("Sueno", 60), ("Ejercicio", 30)):
        respuesta = client.post(
            "/api/v1/registros-tiempo",
            json={
                "categoria_id": categoria_id(client, ana, nombre),
                "inicio": en(minutes=-100),
                "fin": en(minutes=-100 + minutos),
            },
            headers=ana.headers,
        )
        assert respuesta.status_code == 201, respuesta.text
    filas = obtener(client, ana, "carga-vs-descanso")
    assert sum(f["minutos_academicos"] for f in filas) == pytest.approx(10)
    assert sum(f["minutos_sueno"] for f in filas) == pytest.approx(60)
    assert sum(f["minutos_ejercicio"] for f in filas) == pytest.approx(30)


def test_los_reportes_son_solo_del_usuario(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    ids = sembrar(client, ana)
    client.post(
        "/api/v1/metas",
        json={
            "categoria_id": ids["estudio"],
            "tipo": "tiempo_acumulado",
            "periodo": "mes",
            "objetivo": 100,
        },
        headers=ana.headers,
    )
    for ruta in ("agenda", "carga-semanal", "metas", "carga-vs-descanso"):
        assert obtener(client, beto, ruta) == [], ruta
    assert all(f["total"] == 0 for f in obtener(client, beto, "pipeline"))


@pytest.mark.parametrize(
    ("ruta", "params"),
    [
        ("agenda", {"dias": 0}),
        ("agenda", {"limite": 0}),
        ("carga-semanal", {"semanas_atras": -1}),
        ("carga-vs-descanso", {"semanas": 0}),
    ],
)
def test_valida_los_parametros(
    client: TestClient, ana: Sesion, ruta: str, params: dict[str, int]
) -> None:
    respuesta = client.get(f"{BASE}/{ruta}", params=params, headers=ana.headers)
    assert respuesta.status_code == 422


def test_la_agenda_indica_el_tipo_del_evento_y_no_el_de_las_actividades(
    client: TestClient, ana: Sesion
) -> None:
    sembrar(client, ana)
    client.post(
        "/api/v1/eventos",
        json={
            "titulo": "Examen de redes",
            "inicio": en(hours=30),
            "fin": en(hours=32),
            "tipo": "examen",
        },
        headers=ana.headers,
    )
    agenda = {a["titulo"]: a for a in obtener(client, ana, "agenda")}
    assert agenda["Examen de redes"]["subtipo"] == "examen"
    assert agenda["Clase de redes"]["subtipo"] == "personal"
    assert agenda["Reporte de redes"]["subtipo"] is None
