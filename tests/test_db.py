from uuid import uuid4

import pytest

from app.core.db import Pool, fijar_usuario, transaccion

CONSULTA_USUARIO = "select current_setting('app.usuario_id', true) as valor"
CONSULTA_TABLA = "select to_regclass('pg_temp.tabla_prueba') as tabla"


async def test_fijar_usuario_solo_vive_dentro_de_la_transaccion(pool: Pool) -> None:
    usuario_id = uuid4()
    async with transaccion(pool) as conn:
        await fijar_usuario(conn, usuario_id)
        cur = await conn.execute(CONSULTA_USUARIO)
        fila = await cur.fetchone()
        assert fila is not None
        assert fila["valor"] == str(usuario_id)

    async with transaccion(pool) as conn:
        cur = await conn.execute(CONSULTA_USUARIO)
        fila = await cur.fetchone()
        assert fila is not None
        assert fila["valor"] in (None, "")


async def test_transaccion_revierte_si_hay_error(pool: Pool) -> None:
    with pytest.raises(RuntimeError):
        async with transaccion(pool) as conn:
            await conn.execute("create temp table tabla_prueba (x int)")
            raise RuntimeError("falla")

    async with transaccion(pool) as conn:
        cur = await conn.execute(CONSULTA_TABLA)
        fila = await cur.fetchone()
        assert fila is not None
        assert fila["tabla"] is None


async def test_transaccion_confirma_si_no_hay_error(pool: Pool) -> None:
    async with transaccion(pool) as conn:
        await conn.execute("create temp table tabla_prueba (x int)")

    async with transaccion(pool) as conn:
        cur = await conn.execute(CONSULTA_TABLA)
        fila = await cur.fetchone()
        assert fila is not None
        assert fila["tabla"] is not None
