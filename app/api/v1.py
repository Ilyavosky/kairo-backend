from fastapi import APIRouter

from app.modules.actividades.router import router as actividades
from app.modules.auth.router import router as auth
from app.modules.autoevaluaciones.router import router as autoevaluaciones
from app.modules.calendario.router import router as calendario
from app.modules.capturas.router import router as capturas
from app.modules.categorias.router import router as categorias
from app.modules.etiquetas.router import router as etiquetas
from app.modules.eventos.router import router as eventos
from app.modules.interno.router import router as interno
from app.modules.materias.router import router as materias
from app.modules.metas.router import router as metas
from app.modules.recordatorios.router import router as recordatorios
from app.modules.registros_tiempo.router import router as registros_tiempo
from app.modules.telegram.router import router as telegram
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
router.include_router(capturas)
router.include_router(recordatorios)
router.include_router(autoevaluaciones)
router.include_router(telegram)
router.include_router(interno)
