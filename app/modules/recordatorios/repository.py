from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import actualizar_por_id, columnas
from app.modules.recordatorios.schemas import RecordatorioIn

COLUMNAS = (
    "id",
    "actividad_id",
    "evento_id",
    "meta_id",
    "momento",
    "estado_envio",
    "intentos",
    "enviado_en",
    "creado_en",
)


async def listar(
    conn: Conexion,
    estado: str | None,
    desde: datetime | None,
    hasta: datetime | None,
    limite: int,
    desplazamiento: int,
) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from recordatorio "
        "where (%(estado)s::text is null or estado_envio = %(estado)s) "
        "and (%(desde)s::timestamptz is null or momento >= %(desde)s) "
        "and (%(hasta)s::timestamptz is null or momento <= %(hasta)s) "
        "order by momento, id limit %(limite)s offset %(desplazamiento)s"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        {
            "estado": estado,
            "desde": desde,
            "hasta": hasta,
            "limite": limite,
            "desplazamiento": desplazamiento,
        },
    )
    return await cur.fetchall()


async def obtener(conn: Conexion, recordatorio_id: UUID) -> DictRow | None:
    consulta = sql.SQL("select {} from recordatorio where id = %s").format(
        columnas(COLUMNAS)
    )
    cur = await conn.execute(consulta, (recordatorio_id,))
    return await cur.fetchone()


async def crear(conn: Conexion, usuario_id: UUID, datos: RecordatorioIn) -> DictRow:
    consulta = sql.SQL(
        "insert into recordatorio (usuario_id, actividad_id, evento_id, meta_id, "
        "momento) values (%s, %s, %s, %s, %s) returning {}"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        (usuario_id, datos.actividad_id, datos.evento_id, datos.meta_id, datos.momento),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def actualizar(
    conn: Conexion, recordatorio_id: UUID, campos: dict[str, Any]
) -> DictRow | None:
    return await actualizar_por_id(
        conn, "recordatorio", recordatorio_id, campos, frozenset(), COLUMNAS
    )
