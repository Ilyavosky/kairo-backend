from datetime import date
from uuid import UUID

from psycopg.rows import DictRow

from app.core.db import Conexion

COLUMNAS = "semana_desde, estado_animo, satisfaccion, nota, creada_en, actualizada_en"


async def hoy_local(conn: Conexion, usuario_id: UUID) -> date:
    cur = await conn.execute(
        "select (now() at time zone zona_horaria)::date as hoy "
        "from usuario where id = %s",
        (usuario_id,),
    )
    fila = await cur.fetchone()
    assert fila is not None
    hoy: date = fila["hoy"]
    return hoy


async def listar(conn: Conexion, limite: int) -> list[DictRow]:
    cur = await conn.execute(
        f"select {COLUMNAS} from autoevaluacion_semanal "
        "order by semana_desde desc limit %s",
        (limite,),
    )
    return await cur.fetchall()


async def obtener(conn: Conexion, semana: date) -> DictRow | None:
    cur = await conn.execute(
        f"select {COLUMNAS} from autoevaluacion_semanal where semana_desde = %s",
        (semana,),
    )
    return await cur.fetchone()


async def guardar(
    conn: Conexion,
    usuario_id: UUID,
    semana: date,
    estado_animo: int,
    satisfaccion: int,
    nota: str | None,
) -> DictRow:
    cur = await conn.execute(
        "insert into autoevaluacion_semanal "
        "(usuario_id, semana_desde, estado_animo, satisfaccion, nota) "
        "values (%s, %s, %s, %s, %s) "
        "on conflict (usuario_id, semana_desde) do update set "
        "estado_animo = excluded.estado_animo, "
        "satisfaccion = excluded.satisfaccion, nota = excluded.nota "
        f"returning {COLUMNAS}",
        (usuario_id, semana, estado_animo, satisfaccion, nota),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila
