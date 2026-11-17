import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_se_separan_por_coma() -> None:
    settings = Settings(cors_origins="http://a.com, http://b.com ,")
    assert settings.cors_origins_list == ["http://a.com", "http://b.com"]


def test_produccion_exige_secreto_jwt_largo() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="corto")


def test_produccion_acepta_secreto_jwt_largo() -> None:
    settings = Settings(app_env="production", jwt_secret="x" * 32)
    assert settings.app_env == "production"
