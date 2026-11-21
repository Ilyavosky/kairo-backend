from uuid import UUID

from fastapi import APIRouter

from app.core.auth import Ctx
from app.core.errors import ErrorApi
from app.modules.materias import repository
from app.modules.materias.schemas import MateriaIn, MateriaOut, MateriaPatch

router = APIRouter(prefix="/materias", tags=["materias"])


def no_encontrada() -> ErrorApi:
    return ErrorApi(404, "no_encontrado", "La materia no existe")


@router.get("")
async def listar(ctx: Ctx, activa: bool | None = None) -> list[MateriaOut]:
    filas = await repository.listar(ctx.conn, activa)
    return [MateriaOut.model_validate(f) for f in filas]


@router.post("", status_code=201)
async def crear(datos: MateriaIn, ctx: Ctx) -> MateriaOut:
    fila = await repository.crear(ctx.conn, ctx.usuario_id, datos)
    return MateriaOut.model_validate(fila)


@router.get("/{materia_id}")
async def obtener(materia_id: UUID, ctx: Ctx) -> MateriaOut:
    fila = await repository.obtener(ctx.conn, materia_id)
    if fila is None:
        raise no_encontrada()
    return MateriaOut.model_validate(fila)


@router.patch("/{materia_id}")
async def actualizar(materia_id: UUID, datos: MateriaPatch, ctx: Ctx) -> MateriaOut:
    fila = await repository.actualizar(
        ctx.conn, materia_id, datos.model_dump(exclude_unset=True)
    )
    if fila is None:
        raise no_encontrada()
    return MateriaOut.model_validate(fila)
