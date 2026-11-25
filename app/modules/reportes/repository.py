from psycopg.rows import DictRow

from app.core.db import Conexion

LUNES_ACTUAL = (
    "date_trunc('week', now() at time zone "
    "(select zona_horaria from usuario where id = app_usuario_id()))::date"
)


async def agenda(conn: Conexion, dias: int, limite: int) -> list[DictRow]:
    cur = await conn.execute(
        "select tipo, id, titulo, materia_id, materia, categoria, cuando, "
        "prioridad, estado from v_agenda_proxima "
        "where cuando <= now() + make_interval(days => %s) "
        "order by cuando, tipo, id limit %s",
        (dias, limite),
    )
    return await cur.fetchall()


async def carga_semanal(
    conn: Conexion, semanas_atras: int, semanas_adelante: int
) -> list[DictRow]:
    cur = await conn.execute(
        "select semana_desde, materia_id, materia, actividades_con_vencimiento, "
        "actividades_pendientes, minutos_registrados from v_carga_semanal_materia "
        f"where semana_desde between {LUNES_ACTUAL} - %s * 7 "
        f"and {LUNES_ACTUAL} + %s * 7 "
        "order by semana_desde, materia nulls last, materia_id",
        (semanas_atras, semanas_adelante),
    )
    return await cur.fetchall()


async def metas(conn: Conexion) -> list[DictRow]:
    cur = await conn.execute(
        "select meta_id, categoria_id, categoria, tipo, periodo, objetivo, "
        "periodo_desde, periodo_hasta, progreso, cumplida "
        "from v_progreso_metas order by categoria, periodo, meta_id"
    )
    return await cur.fetchall()


async def pipeline(conn: Conexion) -> list[DictRow]:
    cur = await conn.execute(
        "select entidad_tipo, total, pendientes, aceptadas, corregidas, "
        "descartadas, porcentaje_sin_correccion, promedio_campos_corregidos "
        "from v_desempeno_pipeline order by entidad_tipo"
    )
    return await cur.fetchall()


async def carga_vs_descanso(conn: Conexion, semanas: int) -> list[DictRow]:
    cur = await conn.execute(
        "select semana_desde, minutos_academicos, minutos_sueno, "
        "minutos_ejercicio, estado_animo, satisfaccion from v_carga_vs_descanso "
        f"where semana_desde >= {LUNES_ACTUAL} - (%s - 1) * 7 "
        "order by semana_desde",
        (semanas,),
    )
    return await cur.fetchall()
