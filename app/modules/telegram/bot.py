import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

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
from app.services.formato import fecha_legible
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


ETIQUETAS = {
    "titulo": "Título",
    "descripcion": "Descripción",
    "vence_en": "Vence",
    "materia_id": "Materia",
    "categoria_id": "Categoría",
    "prioridad": "Prioridad",
    "modalidad": "Modalidad",
    "actividad_id": "Actividad",
    "inicio": "Inicio",
    "fin": "Fin",
    "nota": "Nota",
    "tipo": "Tipo",
    "periodo": "Periodo",
    "objetivo": "Objetivo",
    "vigente_desde": "Desde",
    "vigente_hasta": "Hasta",
}
ORDEN = {
    "actividad": [
        "titulo",
        "vence_en",
        "materia_id",
        "categoria_id",
        "prioridad",
        "modalidad",
        "descripcion",
    ],
    "registro_tiempo": ["categoria_id", "inicio", "fin", "nota"],
    "meta": [
        "categoria_id",
        "tipo",
        "periodo",
        "objetivo",
        "vigente_desde",
        "vigente_hasta",
    ],
}
FECHAS = {"vence_en", "inicio", "fin", "vigente_desde", "vigente_hasta"}
PRIORIDADES = {1: "muy baja", 2: "baja", 3: "media", 4: "alta", 5: "muy alta"}
MODALIDADES = {"p": "presencial", "l": "en_linea", "x": "mixta"}
NOMBRES_MODALIDAD = {
    "presencial": "Presencial",
    "en_linea": "En línea",
    "mixta": "Mixta",
}


def _valor_legible(
    campo: str,
    valor: Any,
    nombres: dict[str, str],
    zona: ZoneInfo,
    ahora: datetime,
) -> str:
    if campo in {"materia_id", "categoria_id"}:
        return nombres.get(str(valor), "—")
    if campo in FECHAS:
        return fecha_legible(str(valor), zona, ahora)
    if campo == "prioridad":
        return f"{valor} ({PRIORIDADES.get(valor, '—')})"
    if campo == "modalidad":
        return NOMBRES_MODALIDAD.get(str(valor), str(valor))
    if campo in {"tipo", "periodo"}:
        return str(valor).replace("_", " ").capitalize()
    return str(valor)


async def _resumen_captura(
    ctx: Contexto, captura: CapturaOut, preguntar_modalidad: bool = False
) -> Respuesta:
    nombres_entidad = {
        "actividad": "una actividad",
        "registro_tiempo": "un registro de tiempo",
        "meta": "una meta",
    }
    zona = ZoneInfo(await capturas_repo.zona_horaria(ctx.conn, ctx.usuario_id))
    catalogo = [
        *await capturas_repo.categorias(ctx.conn),
        *await capturas_repo.materias_activas(ctx.conn),
    ]
    nombres = {str(identificador): nombre for identificador, nombre in catalogo}
    ahora = datetime.now(UTC)
    omitidos = {"modalidad"} if preguntar_modalidad else set()
    lineas = [f"Entendí {nombres_entidad[captura.entidad_tipo]}:"]
    for campo in ORDEN[captura.entidad_tipo]:
        valor = captura.campos.get(campo)
        if valor is None or campo in omitidos:
            continue
        legible = _valor_legible(campo, valor, nombres, zona, ahora)
        lineas.append(f"• {ETIQUETAS[campo]}: {legible}")
    descartar: Boton = ("Descartar", f"d:{captura.id}")
    if captura.pendientes:
        faltantes = ", ".join(ETIQUETAS.get(p, p).lower() for p in captura.pendientes)
        lineas.append("Falta: " + faltantes)
        lineas.append("Complétalo en la app o descarta este borrador.")
        return Respuesta("\n".join(lineas), [descartar])
    if preguntar_modalidad:
        lineas.append("¿Qué modalidad tiene? Elige una para guardarla.")
        opciones: list[Boton] = [
            (NOMBRES_MODALIDAD[nombre], f"m:{captura.id}:{letra}")
            for letra, nombre in MODALIDADES.items()
        ]
        return Respuesta("\n".join(lineas), [*opciones, descartar])
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
    sin_modalidad = (
        captura.entidad_tipo == "actividad"
        and not captura.pendientes
        and await capturas_repo.modalidad_propuesta(ctx.conn, captura.id) is None
    )
    return await _resumen_captura(ctx, captura, sin_modalidad)


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
    conn: Conexion,
    telegram_id: int,
    accion: str,
    captura_id: UUID,
    modalidad: str | None = None,
) -> Respuesta:
    usuario_id = await repository.usuario_por_telegram(conn, telegram_id)
    if usuario_id is None:
        return Respuesta(SIN_VINCULO)
    await fijar_usuario(conn, usuario_id)
    ctx = Contexto(conn=conn, usuario_id=usuario_id)
    if accion == "m" and modalidad is not None:
        await capturas.confirmar_con(ctx, captura_id, {"modalidad": modalidad})
        return Respuesta(f"Guardado. Modalidad: {NOMBRES_MODALIDAD[modalidad]}.")
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
    modalidad: str | None = None
    if accion == "m":
        dato, _, letra = dato.partition(":")
        modalidad = MODALIDADES.get(letra)
        if modalidad is None:
            return
    try:
        captura_id = UUID(dato)
    except ValueError:
        return
    if accion not in {"c", "d", "m"}:
        return
    try:
        async with transaccion(pool) as conn:
            respuesta = await _resolver_callback(
                conn, callback.remitente.id, accion, captura_id, modalidad
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
