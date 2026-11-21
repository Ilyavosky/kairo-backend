from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import columnas
from app.modules.registros_tiempo.repository import COLUMNAS as COLUMNAS_REGISTRO

SESION = sql.SQL(
    "id, categoria_id, actividad_id, iniciada_en, estado, cerrada_en, "
    "registro_tiempo_id, "
    "floor(extract(epoch from (coalesce(cerrada_en, now()) - iniciada_en)))::int "
    "as transcurrido_s"
)


async def iniciar(
    conn: Conexion, usuario_id: UUID, categoria_id: UUID, actividad_id: UUID | None
) -> DictRow | None:
    consulta = sql.SQL(
        "insert into sesion_temporizador (usuario_id, categoria_id, actividad_id) "
        "values (%s, %s, %s) "
        "on conflict (usuario_id) where estado = 'en_curso' do nothing "
        "returning {}"
    ).format(SESION)
    cur = await conn.execute(consulta, (usuario_id, categoria_id, actividad_id))
    return await cur.fetchone()


async def actual(conn: Conexion) -> DictRow | None:
    consulta = sql.SQL(
        "select {} from sesion_temporizador where estado = 'en_curso'"
    ).format(SESION)
    cur = await conn.execute(consulta)
    return await cur.fetchone()


async def detener(conn: Conexion, usuario_id: UUID, nota: str | None) -> DictRow | None:
    cur = await conn.execute(
        "select id, categoria_id, actividad_id, iniciada_en "
        "from sesion_temporizador where estado = 'en_curso' for update"
    )
    sesion = await cur.fetchone()
    if sesion is None:
        return None
    insertar = sql.SQL(
        "insert into registro_tiempo (usuario_id, categoria_id, actividad_id, "
        "inicio, fin, origen, nota) "
        "values (%s, %s, %s, %s, clock_timestamp(), 'temporizador', %s) "
        "returning {}"
    ).format(columnas(COLUMNAS_REGISTRO))
    cur = await conn.execute(
        insertar,
        (
            usuario_id,
            sesion["categoria_id"],
            sesion["actividad_id"],
            sesion["iniciada_en"],
            nota,
        ),
    )
    registro = await cur.fetchone()
    assert registro is not None
    await conn.execute(
        "update sesion_temporizador "
        "set estado = 'cerrada', cerrada_en = %s, registro_tiempo_id = %s "
        "where id = %s",
        (registro["fin"], registro["id"], sesion["id"]),
    )
    return registro
