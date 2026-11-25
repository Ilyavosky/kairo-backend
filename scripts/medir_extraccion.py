import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.services.extraccion import ExtraccionNoDisponible, crear_extractor
from app.services.resolucion import Catalogo, resolver

CATEGORIAS = [
    "Tarea",
    "Examen",
    "Proyecto",
    "Exposicion",
    "Lectura",
    "Estudio",
    "Sueno",
    "Ejercicio",
    "Meditacion",
    "Videojuegos",
]


async def medir(
    mensajes: list[str], materias: list[str], zona: str, pausa_s: float
) -> None:
    extractor = crear_extractor(get_settings())
    catalogo = Catalogo(
        [(uuid4(), m) for m in materias],
        [(uuid4(), c) for c in CATEGORIAS],
        ZoneInfo(zona),
    )
    nombres = {
        str(id_): nombre for id_, nombre in catalogo.materias + catalogo.categorias
    }
    fallidos = 0
    for indice, texto in enumerate(mensajes, start=1):
        try:
            respuesta = await extractor.extraer(
                texto, [n for _, n in catalogo.materias], CATEGORIAS
            )
        except ExtraccionNoDisponible as exc:
            fallidos += 1
            print(json.dumps({"n": indice, "mensaje": texto, "error": str(exc)}))
            continue
        resolucion = resolver(respuesta.propuesta, catalogo, datetime.now(UTC))
        campos = {
            clave: nombres.get(str(valor), valor)
            for clave, valor in resolucion.campos.items()
        }
        print(
            json.dumps(
                {
                    "n": indice,
                    "mensaje": texto,
                    "entidad_tipo": respuesta.propuesta.entidad_tipo,
                    "confianza": respuesta.confianza,
                    "campos": campos,
                    "pendientes": resolucion.pendientes,
                },
                ensure_ascii=False,
            )
        )
        await asyncio.sleep(pausa_s)
    print(f"# {len(mensajes)} mensajes, {fallidos} sin respuesta")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Corre mensajes reales contra el LLM y muestra la propuesta"
    )
    parser.add_argument("archivo", type=Path, help="un mensaje por linea; # comenta")
    parser.add_argument("--materias", default="", help="nombres separados por coma")
    parser.add_argument("--zona", default="America/Mexico_City")
    parser.add_argument(
        "--pausa", type=float, default=2.5, help="segundos entre llamadas"
    )
    args = parser.parse_args()
    lineas = [m.strip() for m in args.archivo.read_text(encoding="utf-8").splitlines()]
    mensajes = [m for m in lineas if m and not m.startswith("#")]
    materias = [m.strip() for m in args.materias.split(",") if m.strip()]
    asyncio.run(medir(mensajes, materias, args.zona, args.pausa))


if __name__ == "__main__":
    main()
