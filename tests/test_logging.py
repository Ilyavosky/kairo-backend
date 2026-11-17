import json
import logging

from app.core.logging import FormatoJson


def test_formato_json_incluye_campos_y_no_rompe_con_acentos() -> None:
    registro = logging.LogRecord(
        "kairo", logging.INFO, "", 0, "petición %s", ("ok",), None
    )
    carga = json.loads(FormatoJson().format(registro))
    assert carga["nivel"] == "INFO"
    assert carga["logger"] == "kairo"
    assert carga["mensaje"] == "petición ok"
