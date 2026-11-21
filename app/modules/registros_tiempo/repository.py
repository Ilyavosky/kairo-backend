from datetime import datetime
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import actualizar_por_id, columnas
from app.modules.registros_tiempo.schemas import RegistroIn

COLUMNAS = (
    "id",
    "categoria_id",
    "actividad_id",
    "inicio",
    "fin",
    "origen",
    "nota",
    "creado_en",
)
ANULABLES = frozenset({"actividad_id", "nota"})


async def listar(
    conn: Conexion,
    desde: datetime | None,
    hasta: datetime | None,
    categoria_id: UUID | None,
    actividad_id: UUID | None,
    limite: int,
    desplazamiento: int,
) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from registro_tiempo "
        "where (%(desde)s::timestamptz is null or inicio >= %(desde)s) "
        "and (%(hasta)s::timestamptz is null or inicio <= %(hasta)s) "
        "and (%(categoria_id)s::uuid is null or categoria_id = %(categoria_id)s) "
        "and (%(actividad_id)s::uuid is null or actividad_id = %(actividad_id)s) "
        "order by inicio desc, id "
        "limit %(limite)s offset %(desplazamiento)s"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        {
            "desde": desde,
            "hasta": hasta,
            "categoria_id": categoria_id,
            "actividad_id": actividad_id,
            "limite": limite,
            "desplazamiento": desplazamiento,
        },
    )
    return await cur.fetchall()


async def obtener(conn: Conexion, registro_id: UUID) -> DictRow | None:
    consulta = sql.SQL("select {} from registro_tiempo where id = %s").format(
        columnas(COLUMNAS)
    )
    cur = await conn.execute(consulta, (registro_id,))
    return await cur.fetchone()


async def crear(conn: Conexion, usuario_id: UUID, datos: RegistroIn) -> DictRow:
    consulta = sql.SQL(
        "insert into registro_tiempo (usuario_id, categoria_id, actividad_id, "
        "inicio, fin, origen, nota) "
        "values (%s, %s, %s, %s, %s, 'manual', %s) returning {}"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        (
            usuario_id,
            datos.categoria_id,
            datos.actividad_id,
            datos.inicio,
            datos.fin,
            datos.nota,
        ),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def actualizar(
    conn: Conexion, registro_id: UUID, campos: dict[str, object]
) -> DictRow | None:
    return await actualizar_por_id(
        conn, "registro_tiempo", registro_id, campos, ANULABLES, COLUMNAS
    )
