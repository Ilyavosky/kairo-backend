from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import DictRow
from pydantic import BaseModel, ValidationError

from app.core.auth import Contexto
from app.core.config import get_settings
from app.core.errors import ErrorApi
from app.core.limites import verificar
from app.modules.actividades import repository as actividades
from app.modules.actividades.schemas import ActividadIn
from app.modules.capturas import repository
from app.modules.capturas.schemas import CapturaOut
from app.modules.metas import repository as metas
from app.modules.metas.schemas import MetaIn
from app.modules.registros_tiempo import repository as registros
from app.modules.registros_tiempo.schemas import RegistroIn
from app.services.extraccion import ExtraccionNoDisponible, Extractor
from app.services.resolucion import Catalogo, resolver

ENTIDADES: dict[str, type[BaseModel]] = {
    "actividad": ActividadIn,
    "registro_tiempo": RegistroIn,
    "meta": MetaIn,
}


def _no_encontrada() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "La captura no existe")


def _salida(fila: DictRow) -> CapturaOut:
    return CapturaOut.model_validate(fila)


async def crear(ctx: Contexto, extractor: Extractor, texto: str) -> CapturaOut:
    verificar("capturas", str(ctx.usuario_id), get_settings().limite_capturas_por_min)
    conn = ctx.conn
    ahora = datetime.now(UTC)
    zona = ZoneInfo(await repository.zona_horaria(conn, ctx.usuario_id))
    materias = await repository.materias_activas(conn)
    categorias = await repository.categorias(conn)
    fin_periodo = await repository.siguiente_fin_de_periodo(
        conn, ahora.astimezone(zona).date()
    )
    try:
        respuesta = await extractor.extraer(
            texto, [n for _, n in materias], [n for _, n in categorias]
        )
    except ExtraccionNoDisponible as exc:
        raise ErrorApi(
            503,
            "extraccion_no_disponible",
            "No se pudo interpretar el mensaje; usa el formulario manual",
        ) from exc

    resolucion = resolver(
        respuesta.propuesta, Catalogo(materias, categorias, zona, fin_periodo), ahora
    )
    mensaje_id = await repository.crear_mensaje(conn, ctx.usuario_id, texto)
    captura_id = await repository.crear_extraccion(
        conn,
        ctx.usuario_id,
        mensaje_id,
        respuesta.propuesta.entidad_tipo,
        respuesta.propuesta.model_dump(mode="json"),
        resolucion.campos,
        resolucion.pendientes,
        extractor.modelo,
        min(max(respuesta.confianza, 0.0), 1.0),
    )
    fila = await repository.obtener(conn, captura_id)
    assert fila is not None
    return _salida(fila)


async def obtener(ctx: Contexto, captura_id: UUID) -> CapturaOut:
    fila = await repository.obtener(ctx.conn, captura_id)
    if fila is None:
        raise _no_encontrada()
    return _salida(fila)


async def _bloquear_pendiente(ctx: Contexto, captura_id: UUID) -> tuple[DictRow, bool]:
    fila = await repository.obtener(ctx.conn, captura_id, bloquear=True)
    if fila is None:
        raise _no_encontrada()
    if fila["estado"] == "descartada":
        raise ErrorApi(409, "captura_descartada", "La captura fue descartada")
    return fila, fila["estado"] == "pendiente"


def _validar(entidad_tipo: str, campos: dict[str, Any]) -> BaseModel:
    try:
        return ENTIDADES[entidad_tipo].model_validate(campos)
    except ValidationError as exc:
        invalidos = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise ErrorApi(
            422,
            "captura_incompleta",
            "Faltan o son invalidos: " + ", ".join(invalidos),
        ) from exc


async def _insertar(ctx: Contexto, entidad_tipo: str, datos: BaseModel) -> UUID:
    if isinstance(datos, ActividadIn):
        fila = await actividades.crear(ctx.conn, ctx.usuario_id, datos)
    elif isinstance(datos, RegistroIn):
        fila = await registros.crear(ctx.conn, ctx.usuario_id, datos)
    else:
        assert isinstance(datos, MetaIn)
        fila = await metas.crear(ctx.conn, ctx.usuario_id, datos)
    nuevo: UUID = fila["id"]
    return nuevo


def _iguales(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        try:
            return datetime.fromisoformat(a) == datetime.fromisoformat(b)
        except ValueError:
            return a == b
    return bool(a == b)


async def _cerrar_con_fila(
    ctx: Contexto, fila: DictRow, campos: dict[str, Any], tocados: list[str]
) -> CapturaOut:
    datos = _validar(fila["entidad_tipo"], campos)
    valores = datos.model_dump(mode="json")
    cambios = [
        (campo, fila["campos"].get(campo), valores[campo])
        for campo in tocados
        if not _iguales(fila["campos"].get(campo), valores[campo])
    ]
    destino_id = await _insertar(ctx, fila["entidad_tipo"], datos)
    await repository.cerrar(
        ctx.conn,
        fila["id"],
        "corregida" if cambios else "aceptada",
        fila["entidad_tipo"],
        destino_id,
    )
    await repository.crear_correcciones(ctx.conn, ctx.usuario_id, fila["id"], cambios)
    actual = await repository.obtener(ctx.conn, fila["id"])
    assert actual is not None
    return _salida(actual)


async def confirmar(ctx: Contexto, captura_id: UUID) -> CapturaOut:
    fila, pendiente = await _bloquear_pendiente(ctx, captura_id)
    if not pendiente:
        return _salida(fila)
    return await _cerrar_con_fila(ctx, fila, fila["campos"], [])


async def corregir(
    ctx: Contexto, captura_id: UUID, cambios_usuario: dict[str, Any]
) -> CapturaOut:
    fila, pendiente = await _bloquear_pendiente(ctx, captura_id)
    if not pendiente:
        raise ErrorApi(409, "captura_cerrada", "La captura ya fue confirmada")
    permitidos = set(ENTIDADES[fila["entidad_tipo"]].model_fields)
    desconocidos = sorted(set(cambios_usuario) - permitidos)
    if desconocidos:
        raise ErrorApi(
            422, "validacion", "Campos no corregibles: " + ", ".join(desconocidos)
        )
    campos = {**fila["campos"], **cambios_usuario}
    return await _cerrar_con_fila(ctx, fila, campos, list(cambios_usuario))


async def descartar(ctx: Contexto, captura_id: UUID) -> CapturaOut:
    fila = await repository.obtener(ctx.conn, captura_id, bloquear=True)
    if fila is None:
        raise _no_encontrada()
    if fila["estado"] == "descartada":
        return _salida(fila)
    if fila["estado"] != "pendiente":
        raise ErrorApi(409, "captura_cerrada", "La captura ya fue confirmada")
    await repository.cerrar(ctx.conn, captura_id, "descartada")
    actual = await repository.obtener(ctx.conn, captura_id)
    assert actual is not None
    return _salida(actual)


async def confirmar_con(
    ctx: Contexto, captura_id: UUID, complementos: dict[str, Any]
) -> CapturaOut:
    fila, pendiente = await _bloquear_pendiente(ctx, captura_id)
    if not pendiente:
        return _salida(fila)
    return await _cerrar_con_fila(ctx, fila, {**fila["campos"], **complementos}, [])
