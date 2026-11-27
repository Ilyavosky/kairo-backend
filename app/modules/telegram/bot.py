import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import DictRow
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
from app.modules.telegram import comandos, intenciones, repository
from app.modules.telegram.codigos import hash_codigo
from app.modules.telegram.intenciones import Intencion
from app.modules.telegram.respuesta import Respuesta
from app.modules.telegram.schemas import (
    ActualizacionTelegram,
    CallbackTelegram,
    MensajeTelegram,
)
from app.modules.temporizador import repository as temporizador
from app.services.extraccion import Extractor
from app.services.formato import fecha_legible
from app.services.resumen import Redactor
from app.services.telegram import Boton, ClienteTelegram, TelegramError
from app.services.texto import normalizar

logger = logging.getLogger("kairo.telegram")

LIMITE_MENSAJE = 1000
MINUTOS_BORRADOR = 15
MAX_PALABRAS_TITULO = 8
AYUDA = (
    "Escríbeme en lenguaje natural y lo registro. Por ejemplo:\n"
    "• entregar el reporte de redes el viernes a las 6\n"
    "• estudié 2 horas de bases de datos\n"
    "• quiero estudiar 10 horas por semana\n\n"
    "También entiendo preguntas como 'qué me hace falta', 'qué tengo hoy' "
    "o 'cómo voy'.\n\n"
    "Comandos:\n"
    "/pendientes lista lo que tienes por hacer\n"
    "/hoy, /manana y /semana muestran tu agenda\n"
    "/completar <texto> marca una actividad como hecha\n"
    "/tarea <título> crea una tarea rápida\n"
    "/timer <categoría> inicia el temporizador y /timer stop lo detiene\n"
    "/meta muestra el progreso de tus metas\n"
    "/resumen te da un resumen de tu semana\n"
    "/materias y /categorias muestran tus catálogos\n"
    "/cancelar descarta el borrador en curso\n"
    "/ayuda muestra este mensaje"
)
SALUDO = (
    "Hola. Cuéntame qué necesitas: puedo registrar actividades, tiempo y metas, "
    "o mostrarte tus pendientes. Escribe /ayuda para ver ejemplos."
)
PREGUNTA = (
    "No estoy seguro de cómo ayudarte con eso. Puedo mostrarte tus pendientes "
    "(/pendientes), tu agenda (/hoy, /semana) o tus metas (/meta). Para "
    "registrar algo, escríbelo como instrucción, por ejemplo: 'entregar el "
    "reporte de redes el viernes a las 6'."
)
SIN_VINCULO = (
    "Esta cuenta de Telegram no está vinculada a Kairo. "
    "En la app genera un código de vinculación y envíame /vincular CODIGO."
)


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


REQUERIDOS: dict[str, frozenset[str]] = {
    "actividad": frozenset({"titulo", "categoria_id"}),
    "registro_tiempo": frozenset({"categoria_id", "inicio", "fin"}),
    "meta": frozenset({"categoria_id", "objetivo"}),
}
OPCIONALES = {
    "vence_en": "la fecha",
    "materia_id": "la materia",
    "prioridad": "la prioridad",
}
PISTAS = {
    "registro_tiempo": (
        "Dímelo de nuevo con el detalle, por ejemplo: "
        "'estudié 2 horas de bases de datos'."
    ),
    "meta": (
        "Dímelo de nuevo con la cantidad y el periodo, por ejemplo: "
        "'quiero estudiar 10 horas por semana'."
    ),
    "actividad": "Dímelo de nuevo con más detalle o complétalo en la app.",
}
ENTIDADES_ARTICULO = {
    "actividad": "la actividad",
    "registro_tiempo": "el registro de tiempo",
    "meta": "la meta",
}
PALABRAS_DE_FECHA = frozenset(
    {
        "hoy",
        "manana",
        "pasado",
        "lunes",
        "martes",
        "miercoles",
        "jueves",
        "viernes",
        "sabado",
        "domingo",
        "semana",
        "proxima",
        "proximo",
        "mes",
    }
)


def _faltantes(entidad_tipo: str, pendientes: list[str]) -> list[str]:
    return [p for p in pendientes if p in REQUERIDOS[entidad_tipo]]


def _unir(partes: list[str]) -> str:
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _categorias_ordenadas(
    categorias: list[tuple[UUID, str]],
) -> list[tuple[UUID, str]]:
    return sorted(categorias, key=lambda c: normalizar(c[1]))


async def _formato(ctx: Contexto) -> tuple[ZoneInfo, dict[str, str], datetime]:
    zona = ZoneInfo(await capturas_repo.zona_horaria(ctx.conn, ctx.usuario_id))
    catalogo = [
        *await capturas_repo.categorias(ctx.conn),
        *await capturas_repo.materias_activas(ctx.conn),
    ]
    nombres = {str(identificador): nombre for identificador, nombre in catalogo}
    return zona, nombres, datetime.now(UTC)


def _lineas_campos(
    entidad_tipo: str,
    campos: dict[str, Any],
    nombres: dict[str, str],
    zona: ZoneInfo,
    ahora: datetime,
    omitidos: set[str] | None = None,
) -> list[str]:
    lineas = []
    for campo in ORDEN[entidad_tipo]:
        valor = campos.get(campo)
        if valor is None or campo in (omitidos or set()):
            continue
        legible = _valor_legible(campo, valor, nombres, zona, ahora)
        lineas.append(f"• {ETIQUETAS[campo]}: {legible}")
    return lineas


async def _resumen_captura(
    ctx: Contexto, captura: CapturaOut, preguntar_modalidad: bool = False
) -> Respuesta:
    zona, nombres, ahora = await _formato(ctx)
    omitidos = {"modalidad"} if preguntar_modalidad else set()
    entendido = ENTIDADES_ARTICULO[captura.entidad_tipo].replace("la ", "una ", 1)
    entendido = entendido.replace("el ", "un ", 1)
    lineas = [f"Entendí {entendido}:"]
    lineas += _lineas_campos(
        captura.entidad_tipo, captura.campos, nombres, zona, ahora, omitidos
    )
    descartar: Boton = ("Descartar", f"d:{captura.id}")
    faltan = _faltantes(captura.entidad_tipo, captura.pendientes)
    if "titulo" in faltan:
        lineas.append("")
        lineas.append(
            "Me falta el título. ¿Cómo se llama? Respóndeme con el nombre y la guardo."
        )
        return Respuesta("\n".join(lineas), [descartar])
    if faltan == ["categoria_id"]:
        lineas.append("")
        lineas.append("¿En qué categoría va? Elige una:")
        categorias = _categorias_ordenadas(await capturas_repo.categorias(ctx.conn))
        opciones: list[Boton] = [
            (nombre, f"k:{captura.id}:{indice}")
            for indice, (_, nombre) in enumerate(categorias)
        ]
        return Respuesta("\n".join(lineas), [*opciones, descartar])
    if faltan:
        etiquetas = [ETIQUETAS.get(p, p).lower() for p in faltan]
        lineas.append("")
        lineas.append(f"Me falta: {_unir(etiquetas)}. {PISTAS[captura.entidad_tipo]}")
        return Respuesta("\n".join(lineas), [descartar])
    opcionales = [OPCIONALES[p] for p in captura.pendientes if p in OPCIONALES]
    if opcionales:
        lineas.append("")
        lineas.append(f"No pude interpretar {_unir(opcionales)}; se guardará sin eso.")
    if preguntar_modalidad:
        lineas.append("¿Qué modalidad tiene? Elige una para guardarla.")
        modalidades: list[Boton] = [
            (NOMBRES_MODALIDAD[nombre], f"m:{captura.id}:{letra}")
            for letra, nombre in MODALIDADES.items()
        ]
        return Respuesta("\n".join(lineas), [*modalidades, descartar])
    lineas.append("¿Lo guardo?")
    return Respuesta("\n".join(lineas), [("Confirmar", f"c:{captura.id}"), descartar])


async def _guardado(
    ctx: Contexto, captura: CapturaOut, complementos: dict[str, Any] | None = None
) -> Respuesta:
    zona, nombres, ahora = await _formato(ctx)
    campos = {**captura.campos, **(complementos or {})}
    lineas = [f"Listo, guardé {ENTIDADES_ARTICULO[captura.entidad_tipo]}:"]
    lineas += _lineas_campos(captura.entidad_tipo, campos, nombres, zona, ahora)
    return Respuesta("\n".join(lineas))


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


async def _responder_captura(ctx: Contexto, captura: CapturaOut) -> Respuesta:
    sin_modalidad = (
        captura.entidad_tipo == "actividad"
        and not _faltantes(captura.entidad_tipo, captura.pendientes)
        and await capturas_repo.modalidad_propuesta(ctx.conn, captura.id) is None
    )
    return await _resumen_captura(ctx, captura, sin_modalidad)


async def _captura(ctx: Contexto, extractor: Extractor, texto: str) -> Respuesta:
    captura = await capturas.crear(ctx, extractor, texto)
    return await _responder_captura(ctx, captura)


def _es_pregunta(texto: str) -> bool:
    limpio = texto.strip()
    return limpio.endswith("?") or limpio.startswith("¿")


def _parece_titulo(texto: str) -> bool:
    palabras = intenciones.limpiar(texto).split()
    return (
        0 < len(palabras) <= MAX_PALABRAS_TITULO
        and not _es_pregunta(texto)
        and not any(p.isdigit() or p in PALABRAS_DE_FECHA for p in palabras)
    )


async def _borrador(ctx: Contexto) -> DictRow | None:
    return await capturas_repo.ultima_pendiente(ctx.conn, MINUTOS_BORRADOR)


async def _confirmar_borrador(ctx: Contexto) -> Respuesta:
    borrador = await _borrador(ctx)
    if borrador is None:
        return Respuesta(
            "No tengo nada pendiente por confirmar. Cuéntame qué quieres registrar."
        )
    captura = await capturas.obtener(ctx, borrador["id"])
    if _faltantes(captura.entidad_tipo, captura.pendientes) or (
        captura.entidad_tipo == "actividad"
        and await capturas_repo.modalidad_propuesta(ctx.conn, captura.id) is None
    ):
        return await _responder_captura(ctx, captura)
    cerrada = await capturas.confirmar(ctx, captura.id)
    return await _guardado(ctx, cerrada)


async def _cancelar_borrador(ctx: Contexto) -> Respuesta:
    borrador = await _borrador(ctx)
    if borrador is None:
        return Respuesta("No hay nada que cancelar.")
    await capturas.descartar(ctx, borrador["id"])
    return Respuesta("Listo, descarté el borrador.")


async def _categoria_por_defecto(ctx: Contexto) -> UUID | None:
    categorias = await capturas_repo.categorias(ctx.conn)
    return next((i for i, n in categorias if normalizar(n) == "tarea"), None)


async def _titulo_del_borrador(
    ctx: Contexto, borrador: DictRow, texto: str
) -> Respuesta:
    complementos: dict[str, Any] = {"titulo": texto.strip()[:200]}
    if "categoria_id" in borrador["pendientes"]:
        categoria = await _categoria_por_defecto(ctx)
        if categoria is None:
            return Respuesta(
                "No pude asignarle una categoría. Complétala en la app o descarta "
                "el borrador."
            )
        complementos["categoria_id"] = str(categoria)
    captura = await capturas.confirmar_con(ctx, borrador["id"], complementos)
    return await _guardado(ctx, captura, complementos)


async def _por_intencion(
    ctx: Contexto, redactor: Redactor, detectada: intenciones.Detectada
) -> Respuesta | None:
    intencion = detectada.intencion
    if intencion is Intencion.AYUDA:
        return Respuesta(AYUDA)
    if intencion is Intencion.SALUDO:
        return Respuesta(SALUDO)
    if intencion is Intencion.GRACIAS:
        return Respuesta("A ti. Aquí sigo si necesitas algo más.")
    if intencion is Intencion.PENDIENTES:
        return await comandos.pendientes(ctx)
    if intencion is Intencion.HOY:
        return await comandos.agenda(ctx, "hoy")
    if intencion is Intencion.MANANA:
        return await comandos.agenda(ctx, "manana")
    if intencion is Intencion.SEMANA:
        return await comandos.agenda(ctx, "semana")
    if intencion is Intencion.METAS:
        return await _metas(ctx)
    if intencion is Intencion.RESUMEN:
        return await comandos.resumen(ctx, redactor)
    if intencion is Intencion.CANCELAR:
        return await _cancelar_borrador(ctx)
    if intencion is Intencion.CONFIRMAR:
        return await _confirmar_borrador(ctx)
    if intencion is Intencion.TIMER_DETENER:
        return await _timer(ctx, "stop")
    if intencion is Intencion.TIMER_INICIAR:
        return await _timer(ctx, detectada.argumento)
    return await comandos.completar(ctx, detectada.argumento, True)


async def _texto_libre(
    ctx: Contexto, extractor: Extractor, redactor: Redactor, texto: str
) -> Respuesta:
    if len(texto) > LIMITE_MENSAJE:
        return Respuesta(f"El mensaje es muy largo; el máximo es {LIMITE_MENSAJE}.")
    detectada = intenciones.detectar(texto)
    if detectada is not None:
        respuesta = await _por_intencion(ctx, redactor, detectada)
        if respuesta is not None:
            return respuesta
    borrador = await _borrador(ctx)
    if (
        borrador is not None
        and borrador["entidad_tipo"] == "actividad"
        and "titulo" in borrador["pendientes"]
        and _parece_titulo(texto)
    ):
        return await _titulo_del_borrador(ctx, borrador, texto)
    if _es_pregunta(texto):
        return Respuesta(PREGUNTA)
    return await _captura(ctx, extractor, texto)


async def _comando(
    ctx: Contexto, redactor: Redactor, comando: str, resto: str
) -> Respuesta:
    nombre = normalizar(comando)
    if nombre == "/ayuda":
        return Respuesta(AYUDA)
    if nombre == "/tarea":
        return await _tarea(ctx, resto)
    if nombre == "/timer":
        return await _timer(ctx, resto)
    if nombre in {"/meta", "/metas"}:
        return await _metas(ctx)
    if nombre in {"/pendientes", "/pend"}:
        return await comandos.pendientes(ctx)
    if nombre == "/hoy":
        return await comandos.agenda(ctx, "hoy")
    if nombre == "/manana":
        return await comandos.agenda(ctx, "manana")
    if nombre in {"/semana", "/agenda"}:
        return await comandos.agenda(ctx, "semana")
    if nombre in {"/completar", "/hecho"}:
        respuesta = await comandos.completar(ctx, resto, False)
        assert respuesta is not None
        return respuesta
    if nombre == "/resumen":
        return await comandos.resumen(ctx, redactor)
    if nombre == "/cancelar":
        return await _cancelar_borrador(ctx)
    if nombre == "/materias":
        return await comandos.materias(ctx)
    if nombre == "/categorias":
        return await comandos.categorias(ctx)
    return Respuesta("No conozco ese comando. Escribe /ayuda.")


async def _atender(
    conn: Conexion,
    extractor: Extractor,
    redactor: Redactor,
    telegram_id: int,
    texto: str,
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
    if comando.startswith("/"):
        return await _comando(ctx, redactor, comando, resto)
    return await _texto_libre(ctx, extractor, redactor, texto)


async def _ejecutar(
    pool: Pool, extractor: Extractor, redactor: Redactor, telegram_id: int, texto: str
) -> Respuesta:
    try:
        async with transaccion(pool) as conn:
            return await _atender(conn, extractor, redactor, telegram_id, texto)
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
    redactor: Redactor,
    telegram: ClienteTelegram,
    mensaje: MensajeTelegram,
) -> None:
    if mensaje.remitente is None or not mensaje.text or not mensaje.text.strip():
        return
    respuesta = await _ejecutar(
        pool, extractor, redactor, mensaje.remitente.id, mensaje.text.strip()
    )
    await _enviar(telegram, mensaje.chat.id, respuesta)


async def _resolver_callback(
    conn: Conexion,
    telegram_id: int,
    accion: str,
    objetivo: UUID,
    extra: str = "",
) -> Respuesta:
    usuario_id = await repository.usuario_por_telegram(conn, telegram_id)
    if usuario_id is None:
        return Respuesta(SIN_VINCULO)
    await fijar_usuario(conn, usuario_id)
    ctx = Contexto(conn=conn, usuario_id=usuario_id)
    if accion == "f":
        return await comandos.marcar_completada(ctx, objetivo)
    if accion in {"m", "k"}:
        if accion == "m":
            complemento: dict[str, Any] = {"modalidad": MODALIDADES[extra]}
        else:
            categorias = _categorias_ordenadas(await capturas_repo.categorias(conn))
            indice = int(extra)
            if indice >= len(categorias):
                return Respuesta("Esa categoría ya no está disponible. Elige otra.")
            complemento = {"categoria_id": str(categorias[indice][0])}
        captura = await capturas.confirmar_con(ctx, objetivo, complemento)
        return await _guardado(ctx, captura, complemento)
    if accion == "c":
        return await _guardado(ctx, await capturas.confirmar(ctx, objetivo))
    await capturas.descartar(ctx, objetivo)
    return Respuesta("Descartado.")


async def _callback(
    pool: Pool, telegram: ClienteTelegram, callback: CallbackTelegram
) -> None:
    try:
        await telegram.responder_callback(callback.id)
    except TelegramError as exc:
        logger.warning("no se pudo responder el callback: %s", exc)
    accion, _, dato = (callback.data or "").partition(":")
    if accion not in {"c", "d", "m", "k", "f"}:
        return
    extra = ""
    if accion in {"m", "k"}:
        dato, _, extra = dato.partition(":")
    if (accion == "m" and extra not in MODALIDADES) or (
        accion == "k" and not extra.isdigit()
    ):
        return
    try:
        objetivo = UUID(dato)
    except ValueError:
        return
    try:
        async with transaccion(pool) as conn:
            respuesta = await _resolver_callback(
                conn, callback.remitente.id, accion, objetivo, extra
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
    redactor: Redactor,
    telegram: ClienteTelegram,
    actualizacion: ActualizacionTelegram,
) -> None:
    if actualizacion.message is not None:
        await _mensaje(pool, extractor, redactor, telegram, actualizacion.message)
    elif actualizacion.callback_query is not None:
        await _callback(pool, telegram, actualizacion.callback_query)
