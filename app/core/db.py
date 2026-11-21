from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import Settings

type Conexion = AsyncConnection[DictRow]
type Pool = AsyncConnectionPool[Conexion]


def _usar_rol(rol: str) -> Callable[[Conexion], Awaitable[None]]:
    async def configurar(conn: Conexion) -> None:
        await conn.execute(sql.SQL("set role {}").format(sql.Identifier(rol)))
        await conn.commit()

    return configurar


def crear_pool(settings: Settings) -> Pool:
    return AsyncConnectionPool(
        settings.database_url,
        connection_class=AsyncConnection[DictRow],
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        open=False,
        timeout=5.0,
        configure=_usar_rol(settings.db_role) if settings.db_role else None,
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
    )


@asynccontextmanager
async def transaccion(pool: Pool) -> AsyncIterator[Conexion]:
    async with pool.connection() as conn, conn.transaction():
        yield conn


async def get_tx(request: Request) -> AsyncIterator[Conexion]:
    async with transaccion(request.app.state.pool) as conn:
        yield conn


async def fijar_usuario(conn: Conexion, usuario_id: UUID) -> None:
    await conn.execute(
        "select set_config('app.usuario_id', %s, true)", (str(usuario_id),)
    )


Tx = Annotated[Conexion, Depends(get_tx)]
