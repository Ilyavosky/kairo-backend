from datetime import datetime
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import actualizar_por_id, columnas
from app.modules.eventos.schemas import EventoIn

COLUMNAS = (
    "id",
    "materia_id",
    "titulo",
    "descripcion",
    "lugar",
    "inicio",
    "fin",
    "creado_en",
)
ANULABLES = frozenset({"descripcion", "lugar", "materia_id"})


async def listar(
    conn: Conexion,
    desde: datetime | None,
    hasta: datetime | None,
    materia_id: UUID | None,
    limite: int,
    desplazamiento: int,
) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from evento_calendario "
        "where (%(desde)s::timestamptz is null or fin >= %(desde)s) "
        "and (%(hasta)s::timestamptz is null or inicio <= %(hasta)s) "
        "and (%(materia_id)s::uuid is null or materia_id = %(materia_id)s) "
        "order by inicio, id "
        "limit %(limite)s offset %(desplazamiento)s"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        {
            "desde": desde,
            "hasta": hasta,
            "materia_id": materia_id,
            "limite": limite,
            "desplazamiento": desplazamiento,
        },
    )
    return await cur.fetchall()


async def obtener(conn: Conexion, evento_id: UUID) -> DictRow | None:
    consulta = sql.SQL("select {} from evento_calendario where id = %s").format(
        columnas(COLUMNAS)
    )
    cur = await conn.execute(consulta, (evento_id,))
    return await cur.fetchone()


async def crear(conn: Conexion, usuario_id: UUID, datos: EventoIn) -> DictRow:
    consulta = sql.SQL(
        "insert into evento_calendario (usuario_id, materia_id, titulo, "
        "descripcion, lugar, inicio, fin) "
        "values (%s, %s, %s, %s, %s, %s, %s) returning {}"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        (
            usuario_id,
            datos.materia_id,
            datos.titulo,
            datos.descripcion,
            datos.lugar,
            datos.inicio,
            datos.fin,
        ),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def actualizar(
    conn: Conexion, evento_id: UUID, campos: dict[str, object]
) -> DictRow | None:
    return await actualizar_por_id(
        conn, "evento_calendario", evento_id, campos, ANULABLES, COLUMNAS
    )
