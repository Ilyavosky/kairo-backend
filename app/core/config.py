from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETO_DESARROLLO = "secreto-solo-para-desarrollo-no-usar-en-produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/kairo_test"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 5
    db_role: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-20b"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_s: float = 10.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validar_secretos(self) -> Self:
        if self.app_env == "production":
            if len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET requiere 32 caracteres o más en producción"
                )
        elif not self.jwt_secret:
            self.jwt_secret = SECRETO_DESARROLLO
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
