import re
from dataclasses import dataclass
from enum import Enum

from app.services.texto import normalizar


class Intencion(Enum):
    AYUDA = "ayuda"
    SALUDO = "saludo"
    GRACIAS = "gracias"
    PENDIENTES = "pendientes"
    HOY = "hoy"
    MANANA = "manana"
    SEMANA = "semana"
    METAS = "metas"
    RESUMEN = "resumen"
    CANCELAR = "cancelar"
    CONFIRMAR = "confirmar"
    COMPLETAR = "completar"
    TIMER_INICIAR = "timer_iniciar"
    TIMER_DETENER = "timer_detener"


@dataclass(frozen=True)
class Detectada:
    intencion: Intencion
    argumento: str = ""


FRASES: dict[Intencion, frozenset[str]] = {
    Intencion.PENDIENTES: frozenset(
        {
            "que me hace falta hacer",
            "que me hace falta",
            "que falta",
            "que falta por hacer",
            "que me falta",
            "que me falta por hacer",
            "que me falta hacer",
            "que tengo pendiente",
            "que tengo pendientes",
            "que pendientes tengo",
            "pendientes",
            "mis pendientes",
            "tareas pendientes",
            "mis tareas pendientes",
            "por hacer",
            "que debo hacer",
            "que tengo que hacer",
            "que hago",
            "mis tareas",
            "mis actividades",
            "que tareas tengo",
            "que actividades tengo",
            "lista de tareas",
            "lista de pendientes",
            "que hay por hacer",
            "que tengo por hacer",
            "tareas",
            "actividades",
        }
    ),
    Intencion.HOY: frozenset(
        {
            "hoy",
            "que tengo hoy",
            "que hay hoy",
            "para hoy",
            "agenda de hoy",
            "mi agenda de hoy",
            "que hago hoy",
            "que tengo para hoy",
            "que debo hacer hoy",
            "que me toca hoy",
            "que me falta hoy",
        }
    ),
    Intencion.MANANA: frozenset(
        {
            "manana",
            "que tengo manana",
            "que hay manana",
            "para manana",
            "agenda de manana",
            "mi agenda de manana",
            "que hago manana",
            "que tengo para manana",
            "que me toca manana",
        }
    ),
    Intencion.SEMANA: frozenset(
        {
            "semana",
            "esta semana",
            "que tengo esta semana",
            "que tengo en la semana",
            "mi semana",
            "agenda",
            "mi agenda",
            "que hay esta semana",
            "proximos dias",
            "que viene",
            "que sigue",
            "que tengo para esta semana",
            "para esta semana",
            "agenda de la semana",
            "agenda semanal",
            "que me toca esta semana",
        }
    ),
    Intencion.METAS: frozenset(
        {
            "mis metas",
            "metas",
            "como voy",
            "como voy con mis metas",
            "mi progreso",
            "progreso",
            "avance",
            "mi avance",
            "como voy esta semana",
        }
    ),
    Intencion.RESUMEN: frozenset(
        {
            "resumen",
            "un resumen",
            "resumen semanal",
            "resumen de la semana",
            "como me fue",
            "como me va",
            "como voy en la semana",
        }
    ),
    Intencion.CANCELAR: frozenset(
        {
            "cancela",
            "cancelar",
            "cancelalo",
            "descarta",
            "descartar",
            "descartalo",
            "olvidalo",
            "olvida eso",
            "borra eso",
            "no",
            "nel",
            "mejor no",
            "dejalo",
            "dejalo asi",
        }
    ),
    Intencion.CONFIRMAR: frozenset(
        {
            "si",
            "sii",
            "siii",
            "sip",
            "confirmar",
            "confirma",
            "confirmalo",
            "guardalo",
            "guarda",
            "guardar",
            "dale",
            "ok",
            "okay",
            "va",
            "vale",
            "correcto",
            "exacto",
            "asi es",
            "de acuerdo",
            "claro",
        }
    ),
    Intencion.SALUDO: frozenset(
        {
            "hola",
            "holaa",
            "buenas",
            "hey",
            "ey",
            "que onda",
            "que tal",
            "buen dia",
            "buenos dias",
            "buenas tardes",
            "buenas noches",
            "kairo",
        }
    ),
    Intencion.GRACIAS: frozenset(
        {
            "gracias",
            "muchas gracias",
            "mil gracias",
            "te lo agradezco",
            "genial",
            "perfecto",
            "excelente",
            "super",
            "listo gracias",
            "ok gracias",
        }
    ),
    Intencion.AYUDA: frozenset(
        {
            "ayuda",
            "help",
            "que puedes hacer",
            "que haces",
            "como funciona",
            "comandos",
            "menu",
            "para que sirves",
            "como te uso",
            "que sabes hacer",
            "instrucciones",
        }
    ),
}
PREFIJOS = frozenset(
    {"oye", "hey", "ey", "dime", "dame", "muestrame", "ensename", "kairo", "hola"}
)
SUFIJOS = frozenset({"por", "favor", "porfa", "ahora", "ahorita", "gracias", "kairo"})
FINALIZAR = (
    r"(?:ya )?(?:termine|acabe|complete|finalice|entregue|completa|completar|"
    r"marca(?:r)? como (?:hecha|hecho|lista|listo|completada|completado))"
)
REGLAS: tuple[tuple[Intencion, re.Pattern[str]], ...] = (
    (
        Intencion.TIMER_DETENER,
        re.compile(
            r"(?:deten|detener|para|parar|pausa|termina|terminar|stop) "
            r"(?:el |mi )?(?:timer|temporizador|cronometro)"
        ),
    ),
    (
        Intencion.TIMER_INICIAR,
        re.compile(
            r"(?:inicia|iniciar|empieza|empezar|arranca|arrancar|pon|activa) "
            r"(?:el |un |mi )?(?:timer|temporizador|cronometro)"
            r"(?: de (?P<argumento>.+))?"
        ),
    ),
    (
        Intencion.COMPLETAR,
        re.compile(FINALIZAR + r" (?P<argumento>.+)"),
    ),
)


def limpiar(texto: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", normalizar(texto)).split())


def _nucleo(palabras: list[str]) -> str:
    inicio, fin = 0, len(palabras)
    while fin - inicio > 1 and palabras[inicio] in PREFIJOS:
        inicio += 1
    while fin - inicio > 1 and palabras[fin - 1] in SUFIJOS:
        fin -= 1
    return " ".join(palabras[inicio:fin])


def detectar(texto: str) -> Detectada | None:
    limpio = limpiar(texto)
    if not limpio:
        return None
    nucleo = _nucleo(limpio.split())
    for intencion, frases in FRASES.items():
        if nucleo in frases or limpio in frases:
            return Detectada(intencion)
    for intencion, patron in REGLAS:
        coincidencia = patron.fullmatch(limpio)
        if coincidencia is not None:
            grupos = coincidencia.groupdict()
            return Detectada(intencion, (grupos.get("argumento") or "").strip())
    return None
