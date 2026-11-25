import hashlib
import secrets

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGITUD = 8
VIGENCIA_MINUTOS = 10


def generar_codigo() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(LONGITUD))


def hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().upper().encode()).hexdigest()
