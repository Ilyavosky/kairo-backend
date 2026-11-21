from fastapi import APIRouter

from app.core.auth import Ctx
from app.modules.categorias import repository
from app.modules.categorias.schemas import Ambito, CategoriaOut

router = APIRouter(prefix="/categorias", tags=["categorias"])


@router.get("")
async def listar(ctx: Ctx, ambito: Ambito | None = None) -> list[CategoriaOut]:
    filas = await repository.listar(ctx.conn, ambito)
    return [CategoriaOut.model_validate(f) for f in filas]
