from psycopg.rows import DictRow

from app.core.db import Conexion


async def listar(conn: Conexion, ambito: str | None) -> list[DictRow]:
    cur = await conn.execute(
        "select id, nombre, ambito, peso_default, usuario_id is null as del_sistema "
        "from categoria_actividad "
        "where (%(ambito)s::text is null or ambito = %(ambito)s or ambito = 'ambas') "
        "order by del_sistema desc, nombre",
        {"ambito": ambito},
    )
    return await cur.fetchall()
