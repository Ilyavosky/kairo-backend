import logging
from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError

from app.core.auth import Contexto
from app.core.db import Conexion, Pool, fijar_usuario, transaccion
from app.core.errors import ErrorApi
from app.modules.actividades import repository as actividades
from app.modules.actividades.schemas import ActividadIn
from app.modules.capturas import repository as capturas_repo
from app.modules.capturas import service as capturas
from app.modules.capturas.schemas import CapturaOut
from app.modules.metas import repository as metas
from app.modules.telegram import repository
from app.modules.telegram.codigos import hash_codigo
from app.modules.telegram.schemas import (
    ActualizacionTelegram,
    CallbackTelegram,
    MensajeTelegram,
)
from app.modules.temporizador import repository as temporizador
from app.services.extraccion import Extractor
from app.services.telegram import Boton, ClienteTelegram, TelegramError
from app.services.texto import normalizar

logger = logging.getLogger("kairo.telegram")

LIMITE_MENSAJE = 1000
AYUDA = (
    "Escribe lo que necesitas en lenguaje natural, por ejemplo: "
    "'entregar el reporte de redes el viernes a las 6'.\n\n"
    "Comandos:\n"
    "/tarea <título> crea una tarea\n"
    "/timer inicia el temporizador de Estudio\n"
    "/timer <categoría> inicia el temporizador de esa categoría\n"
    "/timer stop lo detiene y guarda el tiempo\n"
    "/meta muestra el progreso de tus metas\n"
    "/ayuda muestra este mensaje"
)
SIN_VINCULO = (
    "Esta cuenta de Telegram no está vinculada a Kairo. "
    "En la app genera un código de vinculación y envíame /vincular CODIGO."
)


@dataclass(frozen=True)
class Respuesta:
    texto: str
    botones: list[Boton] | None = None


def _resumen_captura(captura: CapturaOut) -> Respuesta:
    nombres = {
        "actividad": "una actividad",
        "registro_tiempo": "un registro de tiempo",
        "meta": "una meta",
    }
    lineas = [f"Entendí {nombres[captura.entidad_tipo]}:"]
    lineas += [f"- {k}: {v}" for k, v in captura.campos.items() if v is not None]
    descartar: Boton = ("Descartar", f"d:{captura.id}")
    if captura.pendientes:
        lineas.append("Falta: " + ", ".join(captura.pendientes))
        lineas.append("Complétalo en la app o descarta este borrador.")
        return Respuesta("\n".join(lineas), [descartar])
    lineas.append("¿Lo guardo?")
    return Respuesta("\n".join(lineas), [("Confirmar", f"c:{captura.id}"), descartar])


async def _vincular(conn: Conexion, telegram_id: int, codigo: str) -> Respuesta:
    if not codigo:
        existente = await repository.usuario_por_telegram(conn, telegram_id)
        return Respuesta(AYUDA if existente else SIN_VINCULO)
    usuario = await repository.vincular(conn, hash_codigo(codigo), telegram_id)
    if usuario is None:
        return Respuesta(
            "El código no es válido, ya se usó o expiró. Genera uno nuevo en la app."
        )
    return Respuesta("Cuenta vinculada. Escribe /ayuda para ver qué puedo hacer.")


async def _tarea(ctx: Contexto, titulo: str) -> Respuesta:
    if not titulo:
        return Respuesta("Uso: /tarea <título>")
    categorias = await capturas_repo.categorias(ctx.conn)
    categoria = next((i for i, n in categorias if normalizar(n) == "tarea"), None)
    if categoria is None:
        return Respuesta("No encontré la categoría Tarea.")
    try:
        datos = ActividadIn(titulo=titulo, categoria_id=categoria)
    except ValidationError:
        return Respuesta("El título debe tener entre 1 y 200 caracteres.")
    fila = await actividades.crear(ctx.conn, ctx.usuario_id, datos)
    return Respuesta(f"Tarea creada: {fila['titulo']}")


async def _timer(ctx: Contexto, argumento: str) -> Respuesta:
    pedido = normalizar(argumento)
    if pedido in {"stop", "detener", "parar"}:
        registro = await temporizador.detener(ctx.conn, ctx.usuario_id, None)
        if registro is None:
            return Respuesta("No hay un temporizador en curso.")
        minutos = int((registro["fin"] - registro["inicio"]).total_seconds() // 60)
        return Respuesta(f"Temporizador detenido: {minutos} min registrados.")
    en_curso = await temporizador.actual(ctx.conn)
    if en_curso is not None and not pedido:
        minutos = en_curso["transcurrido_s"] // 60
        return Respuesta(f"Temporizador en curso desde hace {minutos} min.")
    categorias = await capturas_repo.categorias(ctx.conn)
    buscada = pedido or "estudio"
    categoria = next((i for i, n in categorias if normalizar(n) == buscada), None)
    if categoria is None:
        return Respuesta("No encontré esa categoría. Prueba con /timer Estudio.")
    fila = await temporizador.iniciar(ctx.conn, ctx.usuario_id, categoria, None)
    if fila is None:
        return Respuesta("Ya hay un temporizador en curso. Detenlo con /timer stop.")
    return Respuesta("Temporizador iniciado.")


async def _metas(ctx: Contexto) -> Respuesta:
    activas = await metas.listar(ctx.conn, True, None)
    if not activas:
        return Respuesta("No tienes metas activas.")
    categorias = dict(await capturas_repo.categorias(ctx.conn))
    lineas = []
    for meta in activas:
        avance = await metas.progreso(ctx.conn, meta["id"])
        if avance is None:
            continue
        nombre = categorias.get(meta["categoria_id"], "Meta")
        porcentaje = round(float(avance["progreso"]) / avance["objetivo"] * 100)
        unidad = "min" if avance["tipo"] == "tiempo_acumulado" else "eventos"
        lineas.append(
            f"{nombre} ({avance['periodo']}): "
            f"{round(float(avance['progreso']))}/{avance['objetivo']} {unidad} "
            f"({porcentaje}%)"
        )
    return Respuesta("\n".join(lineas) if lineas else "No tienes metas activas.")


async def _captura(ctx: Contexto, extractor: Extractor, texto: str) -> Respuesta:
    if len(texto) > LIMITE_MENSAJE:
        return Respuesta(f"El mensaje es muy largo; el máximo es {LIMITE_MENSAJE}.")
    captura = await capturas.crear(ctx, extractor, texto)
    return _resumen_captura(captura)


async def _atender(
    conn: Conexion, extractor: Extractor, telegram_id: int, texto: str
) -> Respuesta:
    comando, _, resto = texto.partition(" ")
    comando = comando.split("@")[0].lower()
    resto = resto.strip()
    if comando in {"/start", "/vincular"}:
        return await _vincular(conn, telegram_id, resto)
    usuario_id = await repository.usuario_por_telegram(conn, telegram_id)
    if usuario_id is None:
        return Respuesta(SIN_VINCULO)
    await fijar_usuario(conn, usuario_id)
    ctx = Contexto(conn=conn, usuario_id=usuario_id)
    if comando == "/ayuda":
        return Respuesta(AYUDA)
    if comando == "/tarea":
        return await _tarea(ctx, resto)
    if comando == "/timer":
        return await _timer(ctx, resto)
    if comando == "/meta":
        return await _metas(ctx)
    if comando.startswith("/"):
        return Respuesta("No conozco ese comando. Escribe /ayuda.")
    return await _captura(ctx, extractor, texto)


async def _ejecutar(
    pool: Pool, extractor: Extractor, telegram_id: int, texto: str
) -> Respuesta:
    try:
        async with transaccion(pool) as conn:
            return await _atender(conn, extractor, telegram_id, texto)
    except ErrorApi as exc:
        return Respuesta(exc.detalle)
    except Exception:
        logger.exception("error al atender un mensaje del bot")
        return Respuesta("Ocurrió un error. Intenta de nuevo en un momento.")


async def _enviar(
    telegram: ClienteTelegram, chat_id: int, respuesta: Respuesta
) -> None:
    try:
        await telegram.enviar(chat_id, respuesta.texto, respuesta.botones)
    except TelegramError as exc:
        logger.warning("no se pudo responder en Telegram: %s", exc)


async def _mensaje(
    pool: Pool,
    extractor: Extractor,
    telegram: ClienteTelegram,
    mensaje: MensajeTelegram,
) -> None:
    if mensaje.remitente is None or not mensaje.text or not mensaje.text.strip():
        return
    respuesta = await _ejecutar(
        pool, extractor, mensaje.remitente.id, mensaje.text.strip()
    )
    await _enviar(telegram, mensaje.chat.id, respuesta)


async def _resolver_callback(
    conn: Conexion, telegram_id: int, accion: str, captura_id: UUID
) -> Respuesta:
    usuario_id = await repository.usuario_por_telegram(conn, telegram_id)
    if usuario_id is None:
        return Respuesta(SIN_VINCULO)
    await fijar_usuario(conn, usuario_id)
    ctx = Contexto(conn=conn, usuario_id=usuario_id)
    if accion == "c":
        await capturas.confirmar(ctx, captura_id)
        return Respuesta("Guardado.")
    await capturas.descartar(ctx, captura_id)
    return Respuesta("Descartado.")


async def _callback(
    pool: Pool, telegram: ClienteTelegram, callback: CallbackTelegram
) -> None:
    try:
        await telegram.responder_callback(callback.id)
    except TelegramError as exc:
        logger.warning("no se pudo responder el callback: %s", exc)
    accion, _, dato = (callback.data or "").partition(":")
    try:
        captura_id = UUID(dato)
    except ValueError:
        return
    if accion not in {"c", "d"}:
        return
    try:
        async with transaccion(pool) as conn:
            respuesta = await _resolver_callback(
                conn, callback.remitente.id, accion, captura_id
            )
    except ErrorApi as exc:
        respuesta = Respuesta(exc.detalle)
    except Exception:
        logger.exception("error al atender un boton del bot")
        respuesta = Respuesta("Ocurrió un error. Intenta de nuevo en un momento.")
    chat_id = callback.message.chat.id if callback.message else callback.remitente.id
    await _enviar(telegram, chat_id, respuesta)


async def procesar(
    pool: Pool,
    extractor: Extractor,
    telegram: ClienteTelegram,
    actualizacion: ActualizacionTelegram,
) -> None:
    if actualizacion.message is not None:
        await _mensaje(pool, extractor, telegram, actualizacion.message)
    elif actualizacion.callback_query is not None:
        await _callback(pool, telegram, actualizacion.callback_query)
