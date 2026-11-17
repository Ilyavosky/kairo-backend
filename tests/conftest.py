from collections.abc import AsyncIterator

import pytest

from app.core.config import Settings
from app.core.db import Pool, crear_pool


@pytest.fixture
async def pool() -> AsyncIterator[Pool]:
    settings = Settings(db_pool_min_size=1, db_pool_max_size=1)
    pool = crear_pool(settings)
    await pool.open(wait=True, timeout=10)
    yield pool
    await pool.close()
