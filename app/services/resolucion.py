from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.extraccion import (
    Propuesta,
    PropuestaActividad,
    PropuestaMeta,
    PropuestaRegistroTiempo,
)
from app.services.fechas import resolver_fecha, resolver_hora
from app.services.texto import normalizar

CIERRE_DEL_DIA = time(23, 59)
MAX_DURACION_MIN = 24 * 60


@dataclass(frozen=True)
class Catalogo:
    materias: list[tuple[UUID, str]]
    categorias: list[tuple[UUID, str]]
    zona: ZoneInfo
    fin_periodo: date | None = None


@dataclass
class Resolucion:
    campos: dict[str, Any]
    pendientes: list[str] = field(default_factory=list)


def buscar_por_nombre(
    nombre: str | None, opciones: list[tuple[UUID, str]]
) -> UUID | None:
    if not nombre:
        return None
    buscado = normalizar(nombre)
    if not buscado:
        return None
    normalizadas = [(id_, normalizar(n)) for id_, n in opciones]
    exactas = [id_ for id_, n in normalizadas if n == buscado]
    if len(exactas) == 1:
        return exactas[0]
    if exactas or len(buscado) < 3:
        return None
    parciales = [
        id_ for id_, n in normalizadas if len(n) >= 3 and (buscado in n or n in buscado)
    ]
    return parciales[0] if len(parciales) == 1 else None


def _referencia(
    nombre: str | None,
    opciones: list[tuple[UUID, str]],
    campo: str,
    pendientes: list[str],
    obligatoria: bool,
) -> str | None:
    id_ = buscar_por_nombre(nombre, opciones)
    if id_ is None and (nombre or obligatoria):
        pendientes.append(campo)
    return str(id_) if id_ else None


def _combinar(dia: date, hora: time, zona: ZoneInfo) -> datetime:
    return datetime.combine(dia, hora, tzinfo=zona)


def resolver_actividad(
    p: PropuestaActividad, catalogo: Catalogo, ahora: datetime
) -> Resolucion:
    pendientes: list[str] = []
    local = ahora.astimezone(catalogo.zona)

    titulo = p.titulo.strip()
    if not titulo:
        pendientes.append("titulo")

    materia_id = _referencia(
        p.materia, catalogo.materias, "materia_id", pendientes, False
    )
    categoria_id = _referencia(
        p.categoria, catalogo.categorias, "categoria_id", pendientes, True
    )

    vence_en: str | None = None
    if p.fecha_texto or p.hora_texto:
        dia = (
            resolver_fecha(p.fecha_texto, local.date(), "futuro", catalogo.fin_periodo)
            if p.fecha_texto
            else None
        )
        hora = resolver_hora(p.hora_texto) if p.hora_texto else CIERRE_DEL_DIA
        if dia is None or hora is None:
            pendientes.append("vence_en")
        else:
            momento = _combinar(dia, hora, catalogo.zona)
            if momento < local:
                pendientes.append("vence_en")
            else:
                vence_en = momento.isoformat()

    prioridad = 3
    if p.prioridad is not None:
        if 1 <= p.prioridad <= 5:
            prioridad = p.prioridad
        else:
            pendientes.append("prioridad")

    return Resolucion(
        campos={
            "titulo": titulo or None,
            "descripcion": (p.descripcion or "").strip() or None,
            "vence_en": vence_en,
            "prioridad": prioridad,
            "modalidad": p.modalidad or "presencial",
            "materia_id": materia_id,
            "categoria_id": categoria_id,
        },
        pendientes=pendientes,
    )


def resolver_registro_tiempo(
    p: PropuestaRegistroTiempo, catalogo: Catalogo, ahora: datetime
) -> Resolucion:
    pendientes: list[str] = []
    local = ahora.astimezone(catalogo.zona).replace(microsecond=0)

    categoria_id = _referencia(
        p.categoria, catalogo.categorias, "categoria_id", pendientes, True
    )

    duracion: timedelta | None = None
    if p.duracion_min is not None and 0 < p.duracion_min <= MAX_DURACION_MIN:
        duracion = timedelta(minutes=p.duracion_min)

    inicio: datetime | None = None
    fin: datetime | None = None
    if p.hora_texto:
        dia = (
            resolver_fecha(p.fecha_texto, local.date(), "pasado")
            if p.fecha_texto
            else local.date()
        )
        hora = resolver_hora(p.hora_texto)
        if dia is not None and hora is not None:
            inicio = _combinar(dia, hora, catalogo.zona)
    elif not p.fecha_texto and duracion is not None:
        fin = local
        inicio = local - duracion

    if inicio is not None and duracion is not None and fin is None:
        fin = inicio + duracion
    if inicio is None:
        pendientes.append("inicio")
    if fin is None:
        pendientes.append("fin")

    return Resolucion(
        campos={
            "categoria_id": categoria_id,
            "actividad_id": None,
            "inicio": inicio.isoformat() if inicio else None,
            "fin": fin.isoformat() if fin else None,
            "nota": (p.nota or "").strip() or None,
        },
        pendientes=pendientes,
    )


def resolver_meta(p: PropuestaMeta, catalogo: Catalogo) -> Resolucion:
    pendientes: list[str] = []
    categoria_id = _referencia(
        p.categoria, catalogo.categorias, "categoria_id", pendientes, True
    )

    objetivo: int | None = None
    if p.objetivo is not None and p.objetivo > 0:
        objetivo = p.objetivo
        if p.tipo == "tiempo_acumulado" and p.unidad == "horas":
            objetivo = p.objetivo * 60
    if objetivo is None or objetivo > 100000:
        objetivo = None
        pendientes.append("objetivo")

    return Resolucion(
        campos={
            "categoria_id": categoria_id,
            "tipo": p.tipo,
            "periodo": p.periodo,
            "objetivo": objetivo,
            "vigente_desde": None,
            "vigente_hasta": None,
        },
        pendientes=pendientes,
    )


def resolver(propuesta: Propuesta, catalogo: Catalogo, ahora: datetime) -> Resolucion:
    if isinstance(propuesta, PropuestaActividad):
        return resolver_actividad(propuesta, catalogo, ahora)
    if isinstance(propuesta, PropuestaRegistroTiempo):
        return resolver_registro_tiempo(propuesta, catalogo, ahora)
    return resolver_meta(propuesta, catalogo)
