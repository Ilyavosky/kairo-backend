from typing import Literal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.capturas.router import get_extractor
from app.services.extraccion import (
    ExtraccionNoDisponible,
    Propuesta,
    PropuestaActividad,
    PropuestaMeta,
    PropuestaRegistroTiempo,
    RespuestaLLM,
)


class ExtractorFalso:
    modelo = "modelo-falso"

    def __init__(self, propuesta: Propuesta | None, confianza: float = 0.9) -> None:
        self.propuesta = propuesta
        self.confianza = confianza
        self.llamadas: list[tuple[str, list[str], list[str]]] = []

    async def extraer(
        self, texto: str, materias: list[str], categorias: list[str]
    ) -> RespuestaLLM:
        self.llamadas.append((texto, materias, categorias))
        if self.propuesta is None:
            raise ExtraccionNoDisponible("falla simulada")
        return RespuestaLLM(confianza=self.confianza, propuesta=self.propuesta)


def usar_extractor(client: TestClient, extractor: ExtractorFalso) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_extractor] = lambda: extractor


def actividad(
    titulo: str = "Entregar reporte de redes",
    materia: str | None = None,
    categoria: str | None = "Tarea",
    fecha_texto: str | None = None,
    hora_texto: str | None = None,
    prioridad: int | None = None,
    modalidad: Literal["presencial", "en_linea", "mixta"] | None = None,
) -> PropuestaActividad:
    return PropuestaActividad(
        entidad_tipo="actividad",
        titulo=titulo,
        descripcion=None,
        materia=materia,
        categoria=categoria,
        fecha_texto=fecha_texto,
        hora_texto=hora_texto,
        prioridad=prioridad,
        modalidad=modalidad,
    )


def registro(
    categoria: str | None = "Estudio",
    duracion_min: int | None = 90,
    fecha_texto: str | None = None,
    hora_texto: str | None = None,
) -> PropuestaRegistroTiempo:
    return PropuestaRegistroTiempo(
        entidad_tipo="registro_tiempo",
        categoria=categoria,
        duracion_min=duracion_min,
        fecha_texto=fecha_texto,
        hora_texto=hora_texto,
        nota=None,
    )


def meta(
    categoria: str | None = "Ejercicio",
    objetivo: int | None = 2,
    unidad: str | None = "horas",
) -> PropuestaMeta:
    return PropuestaMeta.model_validate(
        {
            "entidad_tipo": "meta",
            "categoria": categoria,
            "tipo": "tiempo_acumulado",
            "periodo": "semana",
            "objetivo": objetivo,
            "unidad": unidad,
        }
    )
