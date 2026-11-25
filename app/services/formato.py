from datetime import datetime
from zoneinfo import ZoneInfo

DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MESES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def fecha_legible(valor: str, zona: ZoneInfo, ahora: datetime) -> str:
    try:
        momento = datetime.fromisoformat(valor)
    except ValueError:
        return valor
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=zona)
    local = momento.astimezone(zona)
    texto = f"{DIAS[local.weekday()]} {local.day} {MESES[local.month - 1]}"
    if local.year != ahora.astimezone(zona).year:
        texto += f" {local.year}"
    return f"{texto}, {local:%H:%M}"
