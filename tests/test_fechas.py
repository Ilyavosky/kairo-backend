from datetime import date, time

import pytest

from app.services.fechas import resolver_fecha, resolver_hora
from app.services.texto import normalizar

SABADO = date(2026, 11, 21)


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("hoy", date(2026, 11, 21)),
        ("mañana", date(2026, 11, 22)),
        ("pasado mañana", date(2026, 11, 23)),
        ("el viernes", date(2026, 11, 27)),
        ("el próximo viernes", date(2026, 11, 27)),
        ("el sábado", date(2026, 11, 28)),
        ("el lunes", date(2026, 11, 23)),
        ("la próxima semana", date(2026, 11, 23)),
        ("la semana que viene", date(2026, 11, 23)),
        ("en 3 días", date(2026, 11, 24)),
        ("dentro de dos semanas", date(2026, 12, 5)),
        ("el 25 de noviembre", date(2026, 11, 25)),
        ("25 de Noviembre de 2027", date(2027, 11, 25)),
        ("1 de enero", date(2027, 1, 1)),
        ("15 de noviembre", date(2027, 11, 15)),
        ("25/11", date(2026, 11, 25)),
        ("25/11/26", date(2026, 11, 25)),
        ("2026-12-01", date(2026, 12, 1)),
        ("el viernes 4 de diciembre", date(2026, 12, 4)),
        ("fin de semestre", None),
        ("31 de febrero", None),
        ("algún día", None),
        ("", None),
    ],
)
def test_fecha_hacia_el_futuro(texto: str, esperada: date | None) -> None:
    assert resolver_fecha(texto, SABADO, "futuro") == esperada


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("ayer", date(2026, 11, 20)),
        ("antier", date(2026, 11, 19)),
        ("el viernes", date(2026, 11, 20)),
        ("el sábado", date(2026, 11, 14)),
        ("la semana pasada", date(2026, 11, 9)),
        ("15 de noviembre", date(2026, 11, 15)),
        ("25 de diciembre", date(2025, 12, 25)),
    ],
)
def test_fecha_hacia_el_pasado(texto: str, esperada: date) -> None:
    assert resolver_fecha(texto, SABADO, "pasado") == esperada


def test_fin_de_periodo_usa_el_calendario_academico() -> None:
    fin = date(2026, 12, 18)
    assert resolver_fecha("al fin de semestre", SABADO, "futuro", fin) == fin
    assert resolver_fecha("fin del periodo", SABADO, "futuro", None) is None


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("a las 5 pm", time(17, 0)),
        ("5:30 pm", time(17, 30)),
        ("11:59 p.m.", time(23, 59)),
        ("12 am", time(0, 0)),
        ("12 pm", time(12, 0)),
        ("8 am", time(8, 0)),
        ("17:00", time(17, 0)),
        ("a las 8 de la mañana", time(8, 0)),
        ("a las 4 de la tarde", time(16, 0)),
        ("a las 7 de la noche", time(19, 0)),
        ("mediodía", time(12, 0)),
        ("a las 5", None),
        ("5:30", None),
        ("25:00", None),
        ("13 pm", None),
        ("", None),
    ],
)
def test_hora(texto: str, esperada: time | None) -> None:
    assert resolver_hora(texto) == esperada


def test_normalizar_quita_acentos_y_mayusculas() -> None:
    assert normalizar("  Cálculo   DIFERENCIAL ") == "calculo diferencial"
    assert normalizar("Ñandú") == "nandu"
