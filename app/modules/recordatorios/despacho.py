import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from psycopg.rows import DictRow
from pydantic import BaseModel

from app.core.db import Conexion, Pool, transaccion
from app.services.telegram import ClienteTelegram, TelegramError

logger = logging.getLogger("kairo.despacho")

MAX_INTENTOS = 3
ETIQUETAS_EVENTO = {
    "clase": "clase",
    "examen": "examen",
    "entrega": "entrega",
    "reunion": "reunión",
}
LOTE = 20

PENDIENTES = """
select
    r.id,
    r.intentos,
    u.telegram_id,
    u.zona_horaria,
    u.activo,
    case
        when r.actividad_id is not null then 'actividad'
        when r.evento_id is not null then 'evento'
        else 'meta'
    end as tipo,
    coalesce(a.titulo, e.titulo, c.nombre) as titulo,
    coalesce(a.vence_en, e.inicio) as cuando,
    e.tipo as subtipo
from recordatorio as r
inner join usuario as u on r.usuario_id = u.id
left join actividad as a on r.actividad_id = a.id
left join evento_calendario as e on r.evento_id = e.id
left join meta as m on r.meta_id = m.id
left join categoria_actividad as c on m.categoria_id = c.id
where r.estado_envio = 'pendiente' and r.momento <= now() and r.intentos < %s
order by r.momento, r.id
limit %s
for update of r skip locked
"""


class ResultadoDespacho(BaseModel):
    procesados: int
    enviados: int
    reintentos: int
    fallidos: int


@dataclass
class Conteo:
    enviados: int = 0
    reintentos: int = 0
    fallidos: int = 0


def _texto(fila: DictRow) -> str:
    titulo = fila["titulo"]
    cuando = fila["cuando"]
    fecha = ""
    if cuando is not None:
        local = cuando.astimezone(ZoneInfo(fila["zona_horaria"]))
        fecha = local.strftime("%d/%m %H:%M")
    if fila["tipo"] == "evento":
        etiqueta = ETIQUETAS_EVENTO.get(fila["subtipo"])
        prefijo = f"Recordatorio ({etiqueta})" if etiqueta else "Recordatorio"
        return f"{prefijo}: {titulo} empieza el {fecha}."
    if fila["tipo"] == "meta":
        return (
            f"Recordatorio: revisa tu meta de {titulo}. Usa /meta para ver el avance."
        )
    if fecha:
        return f"Recordatorio: {titulo} vence el {fecha}."
    return f"Recordatorio: {titulo}."


async def _marcar(
    conn: Conexion,
    id_: object,
    estado: str,
    intentos: int,
    enviado_en: datetime | None,
    error: str | None,
) -> None:
    await conn.execute(
        "update recordatorio set estado_envio = %s, intentos = %s, "
        "enviado_en = %s, ultimo_error = %s where id = %s",
        (estado, intentos, enviado_en, error, id_),
    )


async def _atender(
    conn: Conexion, telegram: ClienteTelegram, fila: DictRow, conteo: Conteo
) -> None:
    intentos = fila["intentos"] + 1
    if not fila["activo"] or fila["telegram_id"] is None:
        motivo = "usuario_inactivo" if not fila["activo"] else "sin_telegram"
        await _marcar(conn, fila["id"], "fallido", intentos, None, motivo)
        conteo.fallidos += 1
        return
    try:
        await telegram.enviar(fila["telegram_id"], _texto(fila))
    except TelegramError as exc:
        definitivo = intentos >= MAX_INTENTOS
        estado = "fallido" if definitivo else "pendiente"
        await _marcar(conn, fila["id"], estado, intentos, None, str(exc)[:200])
        if definitivo:
            conteo.fallidos += 1
        else:
            conteo.reintentos += 1
        return
    await _marcar(conn, fila["id"], "enviado", intentos, datetime.now(UTC), None)
    conteo.enviados += 1


async def despachar(
    pool: Pool, telegram: ClienteTelegram, rol_propio: bool = False
) -> ResultadoDespacho:
    conteo = Conteo()
    async with transaccion(pool) as conn:
        if not rol_propio:
            await conn.execute("set local role kairo_worker")
        cur = await conn.execute(PENDIENTES, (MAX_INTENTOS, LOTE))
        filas = await cur.fetchall()
        for fila in filas:
            await _atender(conn, telegram, fila, conteo)
    logger.info(
        "despacho: %d enviados, %d reintentos, %d fallidos",
        conteo.enviados,
        conteo.reintentos,
        conteo.fallidos,
    )
    return ResultadoDespacho(
        procesados=len(filas),
        enviados=conteo.enviados,
        reintentos=conteo.reintentos,
        fallidos=conteo.fallidos,
    )
