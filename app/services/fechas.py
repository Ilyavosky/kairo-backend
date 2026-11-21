import re
from datetime import date, time, timedelta
from typing import Literal

from app.services.texto import normalizar

Direccion = Literal["futuro", "pasado"]

DIAS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
NUMEROS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}

_NOMBRES_MES = "|".join(MESES)
_NOMBRES_DIA = "|".join(DIAS)
_NUMERO = r"(\d{1,3}|" + "|".join(NUMEROS) + ")"

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DIA_DE_MES = re.compile(rf"\b(\d{{1,2}}) de ({_NOMBRES_MES})(?: de (\d{{4}}))?\b")
_BARRAS = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_FIN_PERIODO = re.compile(
    r"\bfin (?:de|del) (?:periodo|semestre|cuatrimestre|trimestre|curso)\b"
)
_EN_N = re.compile(rf"\b(?:dentro de|en) {_NUMERO} (dias?|semanas?)\b")
_SEMANA_SIGUIENTE = re.compile(
    r"\b(?:(?:proxima|siguiente) semana|semana (?:que viene|proxima|siguiente))\b"
)
_SEMANA_PASADA = re.compile(r"\b(?:semana pasada|semana anterior)\b")
_DIA_SEMANA = re.compile(rf"\b({_NOMBRES_DIA})\b")


def _anio_completo(anio: int) -> int:
    return 2000 + anio if anio < 100 else anio


def _con_anio_inferido(
    hoy: date, mes: int, dia: int, anio: int | None, direccion: Direccion
) -> date | None:
    try:
        if anio is not None:
            return date(anio, mes, dia)
        candidata = date(hoy.year, mes, dia)
        if direccion == "futuro" and candidata < hoy:
            return date(hoy.year + 1, mes, dia)
        if direccion == "pasado" and candidata > hoy:
            return date(hoy.year - 1, mes, dia)
        return candidata
    except ValueError:
        return None


def _lunes(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def resolver_fecha(
    texto: str,
    hoy: date,
    direccion: Direccion = "futuro",
    fin_periodo: date | None = None,
) -> date | None:
    t = normalizar(texto)
    if not t:
        return None

    if m := _ISO.search(t):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if m := _DIA_DE_MES.search(t):
        anio = int(m[3]) if m[3] else None
        return _con_anio_inferido(hoy, MESES[m[2]], int(m[1]), anio, direccion)
    if m := _BARRAS.search(t):
        anio = _anio_completo(int(m[3])) if m[3] else None
        return _con_anio_inferido(hoy, int(m[2]), int(m[1]), anio, direccion)
    if _FIN_PERIODO.search(t):
        return fin_periodo

    if re.search(r"\bpasado manana\b", t):
        return hoy + timedelta(days=2)
    if re.search(r"\b(?:antier|anteayer)\b", t):
        return hoy - timedelta(days=2)
    if re.search(r"\bayer\b", t):
        return hoy - timedelta(days=1)
    if re.search(r"\bmanana\b", t):
        return hoy + timedelta(days=1)
    if re.search(r"\bhoy\b", t):
        return hoy

    if m := _EN_N.search(t):
        cantidad = NUMEROS.get(m[1]) or int(m[1])
        return hoy + timedelta(days=cantidad * (7 if m[2].startswith("semana") else 1))
    if _SEMANA_SIGUIENTE.search(t):
        return _lunes(hoy) + timedelta(days=7)
    if _SEMANA_PASADA.search(t):
        return _lunes(hoy) - timedelta(days=7)

    if m := _DIA_SEMANA.search(t):
        objetivo = DIAS[m[1]]
        if direccion == "futuro":
            salto = (objetivo - hoy.weekday()) % 7 or 7
            return hoy + timedelta(days=salto)
        salto = (hoy.weekday() - objetivo) % 7 or 7
        return hoy - timedelta(days=salto)
    return None


_HORA_AMPM = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b")
_HORA_PARTE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))? (?:de|en|por) la (manana|tarde|noche|madrugada)\b"
)
_HORA_24 = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _hora_valida(hora: int, minuto: int) -> time | None:
    if 0 <= hora < 24 and 0 <= minuto < 60:
        return time(hora, minuto)
    return None


def resolver_hora(texto: str) -> time | None:
    t = normalizar(texto)
    t = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", t)
    if not t:
        return None

    if re.search(r"\bmediodia\b", t):
        return time(12, 0)
    if m := _HORA_AMPM.search(t):
        hora, minuto = int(m[1]), int(m[2] or 0)
        if not 1 <= hora <= 12:
            return None
        if m[3] == "am":
            hora = 0 if hora == 12 else hora
        else:
            hora = 12 if hora == 12 else hora + 12
        return _hora_valida(hora, minuto)
    if m := _HORA_PARTE.search(t):
        hora, minuto = int(m[1]), int(m[2] or 0)
        if not 1 <= hora <= 12:
            return None
        if m[3] in ("tarde", "noche") and hora < 12:
            hora += 12
        elif m[3] == "noche" and hora == 12:
            hora = 0
        return _hora_valida(hora, minuto)
    if m := _HORA_24.search(t):
        hora, minuto = int(m[1]), int(m[2])
        if hora == 0 or hora >= 13:
            return _hora_valida(hora, minuto)
    return None
