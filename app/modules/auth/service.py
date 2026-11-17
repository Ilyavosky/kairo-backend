from psycopg.errors import UniqueViolation

from app.core.config import Settings
from app.core.db import Conexion, fijar_usuario
from app.core.errors import ErrorApi
from app.core.security import (
    HASH_FALSO,
    crear_token,
    hash_password_async,
    verify_password_async,
)
from app.modules.auth import repository
from app.modules.auth.schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut


async def registrar_usuario(conn: Conexion, datos: RegistroIn) -> UsuarioOut:
    password_hash = await hash_password_async(datos.password)
    try:
        usuario_id = await repository.registrar(
            conn,
            datos.email.lower(),
            password_hash,
            datos.nombre,
            datos.zona_horaria,
        )
    except UniqueViolation as exc:
        raise ErrorApi(409, "correo_en_uso", "Ese correo ya está registrado") from exc
    await fijar_usuario(conn, usuario_id)
    fila = await repository.obtener_usuario(conn, usuario_id)
    assert fila is not None
    return UsuarioOut.model_validate(fila)


async def iniciar_sesion(
    conn: Conexion, datos: LoginIn, settings: Settings
) -> TokenOut:
    fila = await repository.buscar_credenciales(conn, datos.email.lower())
    hash_guardado = fila["password_hash"] if fila else HASH_FALSO
    coincide = await verify_password_async(datos.password, hash_guardado)
    if fila is None or not coincide or not fila["activo"]:
        raise ErrorApi(401, "credenciales_invalidas", "Correo o contraseña incorrectos")
    return TokenOut(access_token=crear_token(fila["id"], settings))
