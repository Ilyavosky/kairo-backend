from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.db import Pool, crear_pool
from app.main import create_app
from tests.helpers import Sesion, crear_sesion


@pytest.fixture
async def pool() -> AsyncIterator[Pool]:
    settings = Settings(db_pool_min_size=1, db_pool_max_size=1)
    pool = crear_pool(settings)
    await pool.open(wait=True, timeout=10)
    yield pool
    await pool.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DB_ROLE", "kairo_app")
    monkeypatch.setenv("LIMITES_ACTIVOS", "false")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


@pytest.fixture
def ana(client: TestClient) -> Sesion:
    return crear_sesion(client)


@pytest.fixture
def beto(client: TestClient) -> Sesion:
    return crear_sesion(client)
