from fastapi import APIRouter, Request
from psycopg import Error as PsycopgError
from psycopg_pool import PoolTimeout

from app.core.errors import ErrorApi

router = APIRouter(tags=["salud"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/health/db")
async def health_db(request: Request) -> dict[str, str]:
    try:
        async with request.app.state.pool.connection() as conn:
            await conn.execute("select 1")
    except (PsycopgError, PoolTimeout) as exc:
        raise ErrorApi(
            503, "base_no_disponible", "No hay conexión con la base de datos"
        ) from exc
    return {"status": "healthy", "db": "ok"}
