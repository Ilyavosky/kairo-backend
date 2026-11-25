from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.services.resolucion import (
    Catalogo,
    buscar_por_nombre,
    resolver,
    resolver_meta,
)
from tests.doble_extractor import actividad, meta, registro

ZONA = ZoneInfo("America/Mexico_City")
AHORA = datetime(2026, 11, 21, 10, 0, tzinfo=ZONA)
CALCULO = uuid4()
REDES = uuid4()
REDES_AVANZADAS = uuid4()
TAREA = uuid4()
ESTUDIO = uuid4()
EJERCICIO = uuid4()
CATALOGO = Catalogo(
    materias=[
        (CALCULO, "Cálculo Diferencial"),
        (REDES, "Redes de Computadoras"),
        (REDES_AVANZADAS, "Redes Avanzadas"),
    ],
    categorias=[(TAREA, "Tarea"), (ESTUDIO, "Estudio"), (EJERCICIO, "Ejercicio")],
    zona=ZONA,
)


def test_busqueda_sin_acentos_ni_mayusculas() -> None:
    assert buscar_por_nombre("calculo diferencial", CATALOGO.materias) == CALCULO
    assert buscar_por_nombre("CÁLCULO", CATALOGO.materias) == CALCULO


def test_busqueda_ambigua_o_inexistente_no_adivina() -> None:
    assert buscar_por_nombre("redes", CATALOGO.materias) is None
    assert buscar_por_nombre("Alquimia", CATALOGO.materias) is None
    assert buscar_por_nombre("de", CATALOGO.materias) is None
    assert buscar_por_nombre(None, CATALOGO.materias) is None
    assert buscar_por_nombre("redes avanzadas", CATALOGO.materias) == REDES_AVANZADAS


def _uuid(valor: object) -> UUID:
    return UUID(str(valor))


def test_actividad_con_fecha_relativa_y_materia() -> None:
    r = resolver(
        actividad(materia="calculo", fecha_texto="el viernes", prioridad=4),
        CATALOGO,
        AHORA,
    )
    assert r.pendientes == []
    assert _uuid(r.campos["materia_id"]) == CALCULO
    assert _uuid(r.campos["categoria_id"]) == TAREA
    assert r.campos["vence_en"] == "2026-11-27T23:59:00-06:00"
    assert r.campos["prioridad"] == 4


def test_actividad_con_hora() -> None:
    r = resolver(
        actividad(fecha_texto="mañana", hora_texto="a las 5 pm"), CATALOGO, AHORA
    )
    assert r.campos["vence_en"] == "2026-11-22T17:00:00-06:00"


def test_actividad_sin_fecha_no_marca_pendiente() -> None:
    r = resolver(actividad(), CATALOGO, AHORA)
    assert r.campos["vence_en"] is None
    assert r.pendientes == []


def test_actividad_con_referencias_inexistentes_las_marca() -> None:
    r = resolver(actividad(materia="Alquimia", categoria="Inventada"), CATALOGO, AHORA)
    assert r.campos["materia_id"] is None
    assert r.campos["categoria_id"] is None
    assert r.pendientes == ["materia_id", "categoria_id"]


def test_actividad_con_fecha_pasada_o_ilegible_queda_pendiente() -> None:
    pasada = resolver(actividad(fecha_texto="25/11/2020"), CATALOGO, AHORA)
    assert pasada.campos["vence_en"] is None
    assert pasada.pendientes == ["vence_en"]
    ilegible = resolver(actividad(fecha_texto="cuando pueda"), CATALOGO, AHORA)
    assert ilegible.pendientes == ["vence_en"]
    sin_dia = resolver(actividad(hora_texto="a las 5 pm"), CATALOGO, AHORA)
    assert sin_dia.pendientes == ["vence_en"]
    hora_ambigua = resolver(
        actividad(fecha_texto="mañana", hora_texto="a las 5"), CATALOGO, AHORA
    )
    assert hora_ambigua.pendientes == ["vence_en"]


def test_actividad_con_prioridad_fuera_de_dominio() -> None:
    r = resolver(actividad(prioridad=9), CATALOGO, AHORA)
    assert r.campos["prioridad"] == 3
    assert r.pendientes == ["prioridad"]


def test_actividad_con_titulo_vacio() -> None:
    r = resolver(actividad(titulo="   "), CATALOGO, AHORA)
    assert r.campos["titulo"] is None
    assert r.pendientes == ["titulo"]


def test_registro_sin_fecha_termina_ahora() -> None:
    r = resolver(registro(duracion_min=90), CATALOGO, AHORA)
    assert r.pendientes == []
    assert r.campos["fin"] == "2026-11-21T10:00:00-06:00"
    assert r.campos["inicio"] == "2026-11-21T08:30:00-06:00"


def test_registro_con_hora_y_dia_pasado() -> None:
    r = resolver(
        registro(duracion_min=60, fecha_texto="ayer", hora_texto="4 pm"),
        CATALOGO,
        AHORA,
    )
    assert r.campos["inicio"] == "2026-11-20T16:00:00-06:00"
    assert r.campos["fin"] == "2026-11-20T17:00:00-06:00"


def test_registro_con_dia_pero_sin_hora_no_inventa_el_inicio() -> None:
    r = resolver(registro(duracion_min=60, fecha_texto="ayer"), CATALOGO, AHORA)
    assert r.campos["inicio"] is None
    assert r.campos["fin"] is None
    assert r.pendientes == ["inicio", "fin"]


def test_registro_sin_duracion_valida() -> None:
    r = resolver(registro(duracion_min=None), CATALOGO, AHORA)
    assert r.pendientes == ["inicio", "fin"]
    excesiva = resolver(registro(duracion_min=3000), CATALOGO, AHORA)
    assert "fin" in excesiva.pendientes


def test_meta_convierte_horas_a_minutos() -> None:
    r = resolver(meta(objetivo=2, unidad="horas"), CATALOGO, AHORA)
    assert r.pendientes == []
    assert r.campos["objetivo"] == 120
    assert r.campos["tipo"] == "tiempo_acumulado"
    assert r.campos["periodo"] == "semana"


def test_meta_sin_objetivo_o_categoria_queda_pendiente() -> None:
    r = resolver_meta(meta(categoria="Nada", objetivo=None), CATALOGO)
    assert r.pendientes == ["categoria_id", "objetivo"]
    enorme = resolver_meta(meta(objetivo=999999, unidad="minutos"), CATALOGO)
    assert enorme.pendientes == ["objetivo"]
