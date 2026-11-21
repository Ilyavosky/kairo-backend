import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import ErrorApi

_hasher = PasswordHash.recommended()
HASH_FALSO = _hasher.hash("contrasena-de-relleno")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _hasher.verify(password, hashed)


async def verify_password_async(password: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password, password, hashed)


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


def crear_token(
    usuario_id: UUID, settings: Settings, vigencia: timedelta | None = None
) -> str:
    ahora = datetime.now(UTC)
    vigencia = vigencia or timedelta(minutes=settings.access_token_expire_minutes)
    carga = {"sub": str(usuario_id), "iat": ahora, "exp": ahora + vigencia}
    return jwt.encode(carga, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def leer_token(token: str, settings: Settings) -> UUID:
    try:
        carga = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return UUID(carga["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ErrorApi(401, "token_invalido", "Token inválido o vencido") from exc
