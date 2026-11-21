import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, v1
from app.core.config import get_settings
from app.core.db import crear_pool
from app.core.errors import registrar_manejadores
from app.core.logging import configurar_logging

logger = logging.getLogger("kairo.http")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = crear_pool(get_settings())
    await pool.open()
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configurar_logging(settings.log_level)

    app = FastAPI(title="Kairo API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def registrar_peticion(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inicio = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - inicio) * 1000,
        )
        return response

    registrar_manejadores(app)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
