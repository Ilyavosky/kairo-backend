from datetime import datetime
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import actualizar_por_id, columnas
from app.modules.actividades.schemas import ActividadIn

COLUMNAS = (
    "id",
    "materia_id",
    "categoria_id",
    "titulo",
    "descripcion",
    "vence_en",
    "prioridad",
    "modalidad",
    "estado",
    "creada_en",
    "completada_en",
)
ANULABLES = frozenset({"descripcion", "vence_en", "materia_id"})


async def listar(
    conn: Conexion,
    estado: str | None,
    materia_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
    limite: int,
    desplazamiento: int,
) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from actividad "
        "where (%(estado)s::text is null or estado = %(estado)s) "
        "and (%(materia_id)s::uuid is null or materia_id = %(materia_id)s) "
        "and (%(desde)s::timestamptz is null or vence_en >= %(desde)s) "
        "and (%(hasta)s::timestamptz is null or vence_en <= %(hasta)s) "
        "order by vence_en nulls last, creada_en "
        "limit %(limite)s offset %(desplazamiento)s"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        {
            "estado": estado,
            "materia_id": materia_id,
            "desde": desde,
            "hasta": hasta,
            "limite": limite,
            "desplazamiento": desplazamiento,
        },
    )
    return await cur.fetchall()


async def obtener(conn: Conexion, actividad_id: UUID) -> DictRow | None:
    consulta = sql.SQL("select {} from actividad where id = %s").format(
        columnas(COLUMNAS)
    )
    cur = await conn.execute(consulta, (actividad_id,))
    return await cur.fetchone()


async def crear(conn: Conexion, usuario_id: UUID, datos: ActividadIn) -> DictRow:
    consulta = sql.SQL(
        "insert into actividad (usuario_id, materia_id, categoria_id, titulo, "
        "descripcion, vence_en, prioridad, modalidad) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s) returning {}"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        (
            usuario_id,
            datos.materia_id,
            datos.categoria_id,
            datos.titulo,
            datos.descripcion,
            datos.vence_en,
            datos.prioridad,
            datos.modalidad,
        ),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def actualizar(
    conn: Conexion, actividad_id: UUID, campos: dict[str, object]
) -> DictRow | None:
    return await actualizar_por_id(
        conn, "actividad", actividad_id, campos, ANULABLES, COLUMNAS
    )
