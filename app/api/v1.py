from fastapi import APIRouter

from app.modules.actividades.router import router as actividades
from app.modules.auth.router import router as auth
from app.modules.calendario.router import router as calendario
from app.modules.categorias.router import router as categorias
from app.modules.materias.router import router as materias

router = APIRouter(prefix="/api/v1")
router.include_router(auth)
router.include_router(categorias)
router.include_router(materias)
router.include_router(actividades)
router.include_router(calendario)
