from datetime import datetime

from psycopg.rows import DictRow

from app.core.db import Conexion

ABIERTAS = "a.estado in ('pendiente', 'en_progreso')"


async def abiertas(conn: Conexion, limite: int) -> list[DictRow]:
    cur = await conn.execute(
        "select a.id, a.titulo, a.vence_en, a.prioridad, m.nombre as materia "
        "from actividad as a left join materia as m on m.id = a.materia_id "
        f"where {ABIERTAS} "
        "order by a.vence_en nulls last, a.prioridad desc, a.creada_en limit %s",
        (limite,),
    )
    return await cur.fetchall()


async def contar_abiertas(conn: Conexion) -> int:
    cur = await conn.execute(
        f"select count(*) as n from actividad as a where {ABIERTAS}"
    )
    fila = await cur.fetchone()
    assert fila is not None
    total: int = fila["n"]
    return total


async def contar_vencidas(conn: Conexion) -> int:
    cur = await conn.execute(
        f"select count(*) as n from actividad as a where {ABIERTAS} "
        "and a.vence_en < now()"
    )
    fila = await cur.fetchone()
    assert fila is not None
    total: int = fila["n"]
    return total


async def agenda_entre(
    conn: Conexion, desde: datetime, hasta: datetime, limite: int
) -> list[DictRow]:
    cur = await conn.execute(
        "select tipo, id, titulo, materia, cuando, subtipo from v_agenda_proxima "
        "where cuando >= %s and cuando < %s order by cuando, tipo, id limit %s",
        (desde, hasta, limite),
    )
    return await cur.fetchall()
