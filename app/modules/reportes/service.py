from datetime import UTC, datetime
from typing import Any

from app.core.auth import Contexto
from app.core.config import get_settings
from app.core.limites import verificar
from app.modules.reportes import repository
from app.modules.reportes.schemas import (
    AgendaItem,
    CargaDescansoItem,
    CargaSemanalItem,
    Cifras,
    MetaProgresoItem,
    PipelineItem,
    ResumenOut,
)
from app.services.resumen import RedaccionNoDisponible, Redactor, texto_verificado

CLAVES_INTERNAS = {"id", "materia_id", "meta_id", "categoria_id"}
LARGO_TITULO = 80


async def reunir_cifras(ctx: Contexto) -> Cifras:
    conn = ctx.conn
    return Cifras(
        agenda=[
            AgendaItem.model_validate(f) for f in await repository.agenda(conn, 7, 10)
        ],
        carga_semanal=[
            CargaSemanalItem.model_validate(f)
            for f in await repository.carga_semanal(conn, 1, 1)
        ],
        metas=[
            MetaProgresoItem.model_validate(f) for f in await repository.metas(conn)
        ],
        pipeline=[
            PipelineItem.model_validate(f) for f in await repository.pipeline(conn)
        ],
        carga_vs_descanso=[
            CargaDescansoItem.model_validate(f)
            for f in await repository.carga_vs_descanso(conn, 4)
        ],
    )


def _depurar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _depurar(v) for k, v in valor.items() if k not in CLAVES_INTERNAS}
    if isinstance(valor, list):
        return [_depurar(v) for v in valor]
    if isinstance(valor, str) and len(valor) > LARGO_TITULO:
        return valor[:LARGO_TITULO]
    return valor


def cifras_para_redactor(cifras: Cifras) -> dict[str, Any]:
    depuradas: dict[str, Any] = _depurar(cifras.model_dump(mode="json"))
    return depuradas


async def resumen(ctx: Contexto, redactor: Redactor) -> ResumenOut:
    verificar("resumen", str(ctx.usuario_id), get_settings().limite_resumen_por_min)
    cifras = await reunir_cifras(ctx)
    entrada = cifras_para_redactor(cifras)
    texto: str | None = None
    motivo: str | None = None
    try:
        redactado = await redactor.redactar(entrada)
        if texto_verificado(redactado, entrada):
            texto = redactado
        else:
            motivo = "texto_no_verificado"
    except RedaccionNoDisponible as exc:
        motivo = str(exc)
    return ResumenOut(
        generado_en=datetime.now(UTC),
        cifras=cifras,
        texto=texto,
        modelo=redactor.modelo if texto is not None else None,
        motivo_sin_texto=motivo,
    )
