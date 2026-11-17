from uuid import UUID

from psycopg.rows import DictRow

from app.core.db import Conexion


async def registrar(
    conn: Conexion, email: str, password_hash: str, nombre: str, zona_horaria: str
) -> UUID:
    cur = await conn.execute(
        "select kairo_registrar_usuario(%s, %s, %s, %s) as id",
        (email, password_hash, nombre, zona_horaria),
    )
    fila = await cur.fetchone()
    assert fila is not None
    usuario_id: UUID = fila["id"]
    return usuario_id


async def buscar_credenciales(conn: Conexion, email: str) -> DictRow | None:
    cur = await conn.execute(
        "select id, password_hash, activo from kairo_buscar_credenciales(%s)", (email,)
    )
    return await cur.fetchone()


async def obtener_usuario(conn: Conexion, usuario_id: UUID) -> DictRow | None:
    cur = await conn.execute(
        "select id, email, nombre, zona_horaria, telegram_id, fecha_registro, activo "
        "from usuario where id = %s",
        (usuario_id,),
    )
    return await cur.fetchone()
