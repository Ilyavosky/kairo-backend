import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

logger = logging.getLogger(__name__)


class ErrorApi(Exception):
    def __init__(
        self,
        status_code: int,
        codigo: str,
        detalle: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detalle)
        self.status_code = status_code
        self.codigo = codigo
        self.detalle = detalle
        self.headers = headers


def respuesta_error(
    status_code: int,
    codigo: str,
    detalle: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"codigo": codigo, "detalle": detalle},
        headers=headers,
    )


async def manejar_error_api(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ErrorApi):
        raise exc
    return respuesta_error(exc.status_code, exc.codigo, exc.detalle, exc.headers)


async def manejar_validacion(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    detalle = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
    )
    return respuesta_error(422, "validacion", detalle)


async def manejar_unico(_: Request, __: Exception) -> JSONResponse:
    return respuesta_error(409, "conflicto", "El registro ya existe")


async def manejar_check(_: Request, __: Exception) -> JSONResponse:
    return respuesta_error(
        422, "restriccion_violada", "Los datos no cumplen las reglas del sistema"
    )


async def manejar_referencia(_: Request, __: Exception) -> JSONResponse:
    return respuesta_error(
        422, "referencia_invalida", "Una de las referencias indicadas no existe"
    )


async def manejar_no_controlado(_: Request, exc: Exception) -> JSONResponse:
    logger.error("error no controlado", exc_info=exc)
    return respuesta_error(500, "error_interno", "Error interno del servidor")


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorApi, manejar_error_api)
    app.add_exception_handler(RequestValidationError, manejar_validacion)
    app.add_exception_handler(UniqueViolation, manejar_unico)
    app.add_exception_handler(CheckViolation, manejar_check)
    app.add_exception_handler(ForeignKeyViolation, manejar_referencia)
    app.add_exception_handler(Exception, manejar_no_controlado)
