import time
from collections import deque

from app.core.config import get_settings
from app.core.errors import ErrorApi

VENTANA_S = 60.0
LIMPIEZA_CADA = 10_000

_cubetas: dict[str, deque[float]] = {}


def reiniciar() -> None:
    _cubetas.clear()


def _limpiar(ahora: float) -> None:
    vencidas = [
        clave
        for clave, marcas in _cubetas.items()
        if not marcas or ahora - marcas[-1] >= VENTANA_S
    ]
    for clave in vencidas:
        del _cubetas[clave]


def verificar(nombre: str, clave: str, maximo: int) -> None:
    if not get_settings().limites_activos or maximo <= 0:
        return
    ahora = time.monotonic()
    if len(_cubetas) >= LIMPIEZA_CADA:
        _limpiar(ahora)
    cubeta = _cubetas.setdefault(f"{nombre}:{clave}", deque())
    while cubeta and ahora - cubeta[0] >= VENTANA_S:
        cubeta.popleft()
    if len(cubeta) >= maximo:
        espera = max(1, int(VENTANA_S - (ahora - cubeta[0])) + 1)
        raise ErrorApi(
            429,
            "demasiadas_peticiones",
            f"Demasiados intentos; espera {espera} segundos",
            headers={"Retry-After": str(espera)},
        )
    cubeta.append(ahora)
