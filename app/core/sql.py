from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.errors import ErrorApi


def columnas(nombres: tuple[str, ...]) -> sql.Composable:
    return sql.SQL(", ").join(sql.Identifier(n) for n in nombres)


async def actualizar_por_id(
    conn: Conexion,
    tabla: str,
    id_: UUID,
    campos: dict[str, Any],
    anulables: frozenset[str],
    retorno: tuple[str, ...],
) -> DictRow | None:
    if not campos:
        raise ErrorApi(422, "sin_cambios", "No se indicó ningún campo para actualizar")
    for nombre, valor in campos.items():
        if valor is None and nombre not in anulables:
            raise ErrorApi(422, "campo_no_nulo", f"{nombre} no puede ser nulo")
    asignaciones = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in campos
    )
    consulta = sql.SQL("update {} set {} where id = %s returning {}").format(
        sql.Identifier(tabla), asignaciones, columnas(retorno)
    )
    cur = await conn.execute(consulta, [*campos.values(), id_])
    return await cur.fetchone()
