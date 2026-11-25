import json
from pathlib import Path

from app.main import create_app
from scripts.exportar_openapi import DESTINO, generar

REPORTES = {
    "/api/v1/reportes/agenda",
    "/api/v1/reportes/carga-semanal",
    "/api/v1/reportes/metas",
    "/api/v1/reportes/pipeline",
    "/api/v1/reportes/carga-vs-descanso",
    "/api/v1/reportes/resumen",
}


def test_el_openapi_exportado_esta_al_dia() -> None:
    assert DESTINO == Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
    assert DESTINO.read_text(encoding="utf-8") == generar(), (
        "docs/openapi.json esta desactualizado; ejecuta "
        "`uv run python -m scripts.exportar_openapi`"
    )


def test_el_contrato_publica_los_reportes_y_oculta_lo_interno() -> None:
    rutas = set(json.loads(generar())["paths"])
    assert REPORTES <= rutas
    assert not any("/interno" in ruta for ruta in rutas)


def test_la_version_del_contrato_es_1_0() -> None:
    assert create_app().openapi()["info"]["version"] == "1.0.0"
