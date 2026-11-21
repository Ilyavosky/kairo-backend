from uuid import UUID

from psycopg.rows import DictRow

from app.core.db import Conexion


async def listar(conn: Conexion) -> list[DictRow]:
    cur = await conn.execute("select id, nombre from etiqueta order by lower(nombre)")
    return await cur.fetchall()


async def crear(conn: Conexion, usuario_id: UUID, nombre: str) -> DictRow:
    cur = await conn.execute(
        "insert into etiqueta (usuario_id, nombre) values (%s, %s) "
        "returning id, nombre",
        (usuario_id, nombre),
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def existe_actividad(conn: Conexion, actividad_id: UUID) -> bool:
    cur = await conn.execute("select 1 from actividad where id = %s", (actividad_id,))
    return await cur.fetchone() is not None


async def existe_etiqueta(conn: Conexion, etiqueta_id: UUID) -> bool:
    cur = await conn.execute("select 1 from etiqueta where id = %s", (etiqueta_id,))
    return await cur.fetchone() is not None


async def de_actividad(conn: Conexion, actividad_id: UUID) -> list[DictRow]:
    cur = await conn.execute(
        "select e.id, e.nombre from actividad_etiqueta as ae "
        "join etiqueta as e on e.id = ae.etiqueta_id "
        "where ae.actividad_id = %s order by lower(e.nombre)",
        (actividad_id,),
    )
    return await cur.fetchall()


async def asignar(
    conn: Conexion, usuario_id: UUID, actividad_id: UUID, etiqueta_id: UUID
) -> None:
    await conn.execute(
        "insert into actividad_etiqueta (actividad_id, etiqueta_id, usuario_id) "
        "values (%s, %s, %s) on conflict do nothing",
        (actividad_id, etiqueta_id, usuario_id),
    )


async def quitar(conn: Conexion, actividad_id: UUID, etiqueta_id: UUID) -> bool:
    cur = await conn.execute(
        "delete from actividad_etiqueta "
        "where actividad_id = %s and etiqueta_id = %s returning etiqueta_id",
        (actividad_id, etiqueta_id),
    )
    return await cur.fetchone() is not None
