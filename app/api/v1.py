from fastapi import APIRouter

from app.modules.actividades.router import router as actividades
from app.modules.auth.router import router as auth
from app.modules.calendario.router import router as calendario
from app.modules.categorias.router import router as categorias
from app.modules.etiquetas.router import router as etiquetas
from app.modules.eventos.router import router as eventos
from app.modules.materias.router import router as materias
from app.modules.metas.router import router as metas
from app.modules.registros_tiempo.router import router as registros_tiempo
from app.modules.temporizador.router import router as temporizador

router = APIRouter(prefix="/api/v1")
router.include_router(auth)
router.include_router(categorias)
router.include_router(materias)
router.include_router(actividades)
router.include_router(etiquetas)
router.include_router(eventos)
router.include_router(registros_tiempo)
router.include_router(temporizador)
router.include_router(metas)
router.include_router(calendario)
