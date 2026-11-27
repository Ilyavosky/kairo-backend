import re
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import DictRow

from app.core.auth import Contexto
from app.modules.actividades import repository as actividades
from app.modules.capturas import repository as capturas_repo
from app.modules.reportes import service as reportes
from app.modules.reportes.schemas import Cifras
from app.modules.telegram import consultas
from app.modules.telegram.intenciones import limpiar
from app.modules.telegram.respuesta import Respuesta
from app.services.formato import dia_legible, fecha_legible
from app.services.resumen import Redactor
from app.services.telegram import Boton

LIMITE_LISTA = 10
LIMITE_BOTONES = 6
LIMITE_AGENDA = 30
BUSQUEDA = 50
ARTICULOS = frozenset({"el", "la", "los", "las", "del", "mis", "una", "con"})
SUBTIPOS = {
    "clase": "clase",
    "examen": "examen",
    "entrega": "entrega",
    "reunion": "reunión",
    "personal": "evento",
}
Rango = Literal["hoy", "manana", "semana"]


async def _zona(ctx: Contexto) -> ZoneInfo:
    return ZoneInfo(await capturas_repo.zona_horaria(ctx.conn, ctx.usuario_id))


def _linea_pendiente(n: int, fila: DictRow, zona: ZoneInfo, ahora: datetime) -> str:
    texto = f"{n}. {fila['titulo']}"
    vence: datetime | None = fila["vence_en"]
    if vence is None:
        texto += " — sin fecha"
    else:
        texto += f" — {fecha_legible(vence.isoformat(), zona, ahora)}"
        if vence < ahora:
            texto += " (vencida)"
    if fila["materia"]:
        texto += f" · {fila['materia']}"
    return texto


def _botones_hechas(filas: list[DictRow]) -> list[Boton]:
    return [
        (f"Hecha {n}", f"f:{fila['id']}")
        for n, fila in enumerate(filas[:LIMITE_BOTONES], 1)
    ]


async def pendientes(ctx: Contexto) -> Respuesta:
    filas = await consultas.abiertas(ctx.conn, LIMITE_LISTA)
    if not filas:
        return Respuesta(
            "No tienes nada pendiente. Si quieres registrar algo, escríbemelo: "
            "'entregar el reporte de redes el viernes a las 6'."
        )
    zona = await _zona(ctx)
    ahora = datetime.now(UTC)
    lineas = ["Esto tienes pendiente:"]
    lineas += [_linea_pendiente(n, f, zona, ahora) for n, f in enumerate(filas, 1)]
    total = await consultas.contar_abiertas(ctx.conn)
    if total > len(filas):
        lineas.append(f"Mostrando {len(filas)} de {total}.")
    lineas.append("Marca una como hecha con los botones o con /completar <texto>.")
    return Respuesta("\n".join(lineas), _botones_hechas(filas))


async def agenda(ctx: Contexto, rango: Rango) -> Respuesta:
    zona = await _zona(ctx)
    ahora = datetime.now(UTC)
    inicio_hoy = datetime.combine(ahora.astimezone(zona).date(), time.min, tzinfo=zona)
    if rango == "hoy":
        desde, hasta = ahora, inicio_hoy + timedelta(days=1)
        titulo, vacio = "Hoy", "No tienes nada programado para hoy."
    elif rango == "manana":
        desde, hasta = inicio_hoy + timedelta(days=1), inicio_hoy + timedelta(days=2)
        titulo, vacio = "Mañana", "No tienes nada programado para mañana."
    else:
        desde, hasta = ahora, ahora + timedelta(days=7)
        titulo = "Los próximos 7 días"
        vacio = "No tienes nada programado en los próximos 7 días."
    filas = await consultas.agenda_entre(ctx.conn, desde, hasta, LIMITE_AGENDA)
    lineas = [f"{titulo}:"] if filas else [vacio]
    dia_actual = None
    for fila in filas:
        local: datetime = fila["cuando"].astimezone(zona)
        if rango == "semana" and local.date() != dia_actual:
            dia_actual = local.date()
            lineas.append(dia_legible(local, zona))
        etiqueta = ""
        if fila["tipo"] == "evento":
            etiqueta = f" ({SUBTIPOS.get(fila['subtipo'], 'evento')})"
        materia = f" · {fila['materia']}" if fila["materia"] else ""
        lineas.append(f"• {local:%H:%M} {fila['titulo']}{etiqueta}{materia}")
    if rango == "hoy":
        vencidas = await consultas.contar_vencidas(ctx.conn)
        if vencidas:
            plural = "actividad vencida" if vencidas == 1 else "actividades vencidas"
            lineas.append(f"Además tienes {vencidas} {plural}. Revisa /pendientes.")
    return Respuesta("\n".join(lineas))


def _buscar(argumento: str, filas: list[DictRow]) -> list[DictRow]:
    buscado = limpiar(argumento)
    exactas = [f for f in filas if limpiar(f["titulo"]) == buscado]
    if len(exactas) == 1:
        return exactas
    palabras = [p for p in buscado.split() if len(p) >= 3 and p not in ARTICULOS]
    if not palabras:
        return []
    return [f for f in filas if all(p in limpiar(f["titulo"]) for p in palabras)]


async def marcar_completada(ctx: Contexto, actividad_id: UUID) -> Respuesta:
    actual = await actividades.obtener(ctx.conn, actividad_id)
    if actual is None:
        return Respuesta("No encontré esa actividad.")
    if actual["estado"] == "completada":
        return Respuesta(f"«{actual['titulo']}» ya estaba completada.")
    fila = await actividades.actualizar(
        ctx.conn, actividad_id, {"estado": "completada"}
    )
    if fila is None:
        return Respuesta("No encontré esa actividad.")
    return Respuesta(f"Listo, marqué «{fila['titulo']}» como completada.")


def _elegir(filas: list[DictRow], encabezado: str) -> Respuesta:
    visibles = filas[:LIMITE_BOTONES]
    lineas = [encabezado] + [f"{n}. {f['titulo']}" for n, f in enumerate(visibles, 1)]
    botones: list[Boton] = [
        (str(n), f"f:{fila['id']}") for n, fila in enumerate(visibles, 1)
    ]
    return Respuesta("\n".join(lineas), botones)


async def completar(
    ctx: Contexto, argumento: str, en_texto_libre: bool
) -> Respuesta | None:
    filas = await consultas.abiertas(ctx.conn, BUSQUEDA)
    sin_resultado = (
        None
        if en_texto_libre
        else Respuesta(
            "No encontré una actividad abierta con ese nombre. Revisa /pendientes."
        )
    )
    if not filas:
        return (
            None if en_texto_libre else Respuesta("No tienes actividades pendientes.")
        )
    if not argumento.strip():
        return _elegir(filas, "¿Cuál completaste?")
    if en_texto_libre and re.search(r"\d|hora|minuto", limpiar(argumento)):
        return None
    coincidencias = _buscar(argumento, filas)
    if not coincidencias:
        return sin_resultado
    if len(coincidencias) == 1:
        return await marcar_completada(ctx, coincidencias[0]["id"])
    return _elegir(coincidencias, "Encontré varias, ¿cuál completaste?")


def _lista(encabezado: str, vacio: str, nombres: list[str]) -> Respuesta:
    if not nombres:
        return Respuesta(vacio)
    return Respuesta("\n".join([encabezado, *(f"• {n}" for n in sorted(nombres))]))


async def materias(ctx: Contexto) -> Respuesta:
    nombres = [n for _, n in await capturas_repo.materias_activas(ctx.conn)]
    return _lista(
        "Tus materias activas:",
        "No tienes materias activas. Créalas en la app.",
        nombres,
    )


async def categorias(ctx: Contexto) -> Respuesta:
    nombres = [n for _, n in await capturas_repo.categorias(ctx.conn)]
    return _lista("Categorías disponibles:", "No hay categorías disponibles.", nombres)


def _texto_cifras(cifras: Cifras, zona: ZoneInfo) -> str:
    lineas = ["No pude redactar el resumen, pero estas son tus cifras:"]
    if cifras.agenda:
        lineas.append(f"Próximos 7 días: {len(cifras.agenda)} pendientes o eventos.")
        for item in cifras.agenda[:3]:
            lineas.append(f"• {dia_legible(item.cuando, zona)}: {item.titulo}")
    for meta in cifras.metas:
        unidad = "min" if meta.tipo == "tiempo_acumulado" else "eventos"
        lineas.append(
            f"Meta {meta.categoria} ({meta.periodo}): {round(meta.progreso)}/"
            f"{meta.objetivo} {unidad} ({round(meta.porcentaje)}%)"
        )
    if len(lineas) == 1:
        return "Todavía no hay datos suficientes para un resumen."
    return "\n".join(lineas)


async def resumen(ctx: Contexto, redactor: Redactor) -> Respuesta:
    resultado = await reportes.resumen(ctx, redactor)
    if resultado.texto:
        return Respuesta(resultado.texto)
    return Respuesta(_texto_cifras(resultado.cifras, await _zona(ctx)))
