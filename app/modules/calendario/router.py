from fastapi import APIRouter

from app.core.auth import Ctx
from app.modules.calendario.schemas import EventoCalendarioOut, TipoCalendario

router = APIRouter(prefix="/calendario", tags=["calendario"])


@router.get("")
async def listar(
    ctx: Ctx, periodo: str | None = None, tipo: TipoCalendario | None = None
) -> list[EventoCalendarioOut]:
    cur = await ctx.conn.execute(
        "select id, periodo, tipo, fecha, fecha_fin, descripcion "
        "from calendario_academico "
        "where (%(periodo)s::text is null or periodo = %(periodo)s) "
        "and (%(tipo)s::text is null or tipo = %(tipo)s) "
        "order by fecha",
        {"periodo": periodo, "tipo": tipo},
    )
    return [EventoCalendarioOut.model_validate(f) for f in await cur.fetchall()]
