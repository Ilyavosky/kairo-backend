from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import actualizar_por_id, columnas
from app.modules.materias.schemas import MateriaIn

COLUMNAS = ("id", "nombre", "docente", "clave", "periodo", "activa")
ANULABLES = frozenset({"docente", "clave"})


async def listar(conn: Conexion, activa: bool | None) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from materia "
        "where (%(activa)s::boolean is null or activa = %(activa)s) order by nombre"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(consulta, {"activa": activa})
    return await cur.fetchall()


async def obtener(conn: Conexion, materia_id: UUID) -> DictRow | None:
    consulta = sql.SQL("select {} from materia where id = %s").format(
        columnas(COLUMNAS)
    )
    cur = await conn.execute(consulta, (materia_id,))
    return await cur.fetchone()


async def crear(conn: Conexion, usuario_id: UUID, datos: MateriaIn) -> DictRow:
    consulta = sql.SQL(
        "insert into materia (usuario_id, nombre, docente, clave, periodo) "
        "values (%s, %s, %s, %s, %s) returning {}"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        (usuario_id, datos.nombre, datos.docente, datos.clave, datos.periodo),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def actualizar(
    conn: Conexion, materia_id: UUID, campos: dict[str, object]
) -> DictRow | None:
    return await actualizar_por_id(
        conn, "materia", materia_id, campos, ANULABLES, COLUMNAS
    )
