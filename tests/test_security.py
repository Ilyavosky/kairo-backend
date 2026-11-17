from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import ErrorApi
from app.core.security import crear_token, hash_password, leer_token, verify_password

SETTINGS = Settings(jwt_secret="x" * 40)


def test_hash_y_verificacion_de_contrasena() -> None:
    hash_ = hash_password("contrasena-segura")
    assert hash_ != "contrasena-segura"
    assert verify_password("contrasena-segura", hash_)
    assert not verify_password("otra-contrasena", hash_)


def test_token_ida_y_vuelta() -> None:
    usuario_id = uuid4()
    assert leer_token(crear_token(usuario_id, SETTINGS), SETTINGS) == usuario_id


def test_token_vencido_se_rechaza() -> None:
    token = crear_token(uuid4(), SETTINGS, vigencia=timedelta(seconds=-5))
    with pytest.raises(ErrorApi) as info:
        leer_token(token, SETTINGS)
    assert info.value.status_code == 401


def test_token_firmado_con_otro_secreto_se_rechaza() -> None:
    token = crear_token(uuid4(), Settings(jwt_secret="y" * 40))
    with pytest.raises(ErrorApi):
        leer_token(token, SETTINGS)
