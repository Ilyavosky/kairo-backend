from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.db import Conexion, Tx, fijar_usuario
from app.core.errors import ErrorApi
from app.core.security import leer_token

esquema_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Contexto:
    conn: Conexion
    usuario_id: UUID


async def get_contexto(
    tx: Tx,
    credenciales: Annotated[
        HTTPAuthorizationCredentials | None, Depends(esquema_bearer)
    ],
) -> Contexto:
    if credenciales is None:
        raise ErrorApi(401, "no_autenticado", "Falta el token de acceso")
    usuario_id = leer_token(credenciales.credentials, get_settings())
    await fijar_usuario(tx, usuario_id)
    return Contexto(conn=tx, usuario_id=usuario_id)


Ctx = Annotated[Contexto, Depends(get_contexto)]
