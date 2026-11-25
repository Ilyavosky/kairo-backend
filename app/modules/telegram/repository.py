from datetime import datetime
from uuid import UUID

from app.core.db import Conexion


async def crear_vinculo(
    conn: Conexion, usuario_id: UUID, codigo_hash: str, minutos: int
) -> datetime:
    cur = await conn.execute(
        "insert into vinculo_telegram (usuario_id, codigo_hash, expira_en) "
        "values (%s, %s, now() + make_interval(mins => %s)) returning expira_en",
        (usuario_id, codigo_hash, minutos),
    )
    fila = await cur.fetchone()
    assert fila is not None
    expira: datetime = fila["expira_en"]
    return expira


async def vincular(conn: Conexion, codigo_hash: str, telegram_id: int) -> UUID | None:
    cur = await conn.execute(
        "select kairo_vincular_telegram(%s, %s) as usuario_id",
        (codigo_hash, telegram_id),
    )
    fila = await cur.fetchone()
    assert fila is not None
    usuario: UUID | None = fila["usuario_id"]
    return usuario


async def usuario_por_telegram(conn: Conexion, telegram_id: int) -> UUID | None:
    cur = await conn.execute(
        "select kairo_usuario_por_telegram(%s) as usuario_id", (telegram_id,)
    )
    fila = await cur.fetchone()
    assert fila is not None
    usuario: UUID | None = fila["usuario_id"]
    return usuario
