from datetime import date
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from app.core.db import Conexion

DESTINOS = {
    "actividad": "actividad_id",
    "registro_tiempo": "registro_tiempo_id",
    "meta": "meta_id",
}

SELECCION = (
    "select e.id, m.texto as mensaje, e.entidad_tipo, e.estado, e.modelo, "
    "e.confianza, e.resuelta as campos, e.pendientes, "
    "coalesce(e.actividad_id, e.registro_tiempo_id, e.meta_id) as resultado_id, "
    "e.creada_en, e.resuelta_en "
    "from extraccion as e "
    "inner join mensaje_origen as m on m.id = e.mensaje_origen_id "
    "where e.id = %s"
)


async def zona_horaria(conn: Conexion, usuario_id: UUID) -> str:
    cur = await conn.execute(
        "select zona_horaria from usuario where id = %s", (usuario_id,)
    )
    fila = await cur.fetchone()
    assert fila is not None
    return str(fila["zona_horaria"])


async def materias_activas(conn: Conexion) -> list[tuple[UUID, str]]:
    cur = await conn.execute("select id, nombre from materia where activa")
    return [(f["id"], f["nombre"]) for f in await cur.fetchall()]


async def categorias(conn: Conexion) -> list[tuple[UUID, str]]:
    cur = await conn.execute("select id, nombre from categoria_actividad")
    return [(f["id"], f["nombre"]) for f in await cur.fetchall()]


async def siguiente_fin_de_periodo(conn: Conexion, desde: date) -> date | None:
    cur = await conn.execute(
        "select fecha from calendario_academico "
        "where tipo = 'fin_periodo' and fecha >= %s order by fecha limit 1",
        (desde,),
    )
    fila = await cur.fetchone()
    if fila is None:
        return None
    fecha: date = fila["fecha"]
    return fecha


async def crear_mensaje(
    conn: Conexion, usuario_id: UUID, texto: str, canal: str = "app"
) -> UUID:
    cur = await conn.execute(
        "insert into mensaje_origen (usuario_id, canal, texto) "
        "values (%s, %s, %s) returning id",
        (usuario_id, canal, texto),
    )
    fila = await cur.fetchone()
    assert fila is not None
    nuevo: UUID = fila["id"]
    return nuevo


async def crear_extraccion(
    conn: Conexion,
    usuario_id: UUID,
    mensaje_id: UUID,
    entidad_tipo: str,
    propuesta: dict[str, Any],
    resuelta: dict[str, Any],
    pendientes: list[str],
    modelo: str,
    confianza: float | None,
) -> UUID:
    cur = await conn.execute(
        "insert into extraccion (usuario_id, mensaje_origen_id, entidad_tipo, "
        "propuesta, resuelta, pendientes, modelo, confianza) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s) returning id",
        (
            usuario_id,
            mensaje_id,
            entidad_tipo,
            Jsonb(propuesta),
            Jsonb(resuelta),
            pendientes,
            modelo,
            confianza,
        ),
    )
    fila = await cur.fetchone()
    assert fila is not None
    nuevo: UUID = fila["id"]
    return nuevo


async def obtener(
    conn: Conexion, captura_id: UUID, bloquear: bool = False
) -> DictRow | None:
    consulta = SELECCION + (" for update of e" if bloquear else "")
    cur = await conn.execute(consulta, (captura_id,))
    return await cur.fetchone()


async def cerrar(
    conn: Conexion,
    captura_id: UUID,
    estado: str,
    entidad_tipo: str | None = None,
    destino_id: UUID | None = None,
) -> None:
    if entidad_tipo is None:
        await conn.execute(
            "update extraccion set estado = %s, resuelta_en = now() where id = %s",
            (estado, captura_id),
        )
        return
    consulta = sql.SQL(
        "update extraccion set estado = %s, {} = %s, resuelta_en = now() where id = %s"
    ).format(sql.Identifier(DESTINOS[entidad_tipo]))
    await conn.execute(consulta, (estado, destino_id, captura_id))


async def crear_correcciones(
    conn: Conexion,
    usuario_id: UUID,
    captura_id: UUID,
    cambios: list[tuple[str, Any, Any]],
) -> None:
    for campo, propuesto, final in cambios:
        await conn.execute(
            "insert into correccion_campo "
            "(usuario_id, extraccion_id, campo, valor_propuesto, valor_final) "
            "values (%s, %s, %s, %s, %s)",
            (usuario_id, captura_id, campo, Jsonb(propuesto), Jsonb(final)),
        )


async def metricas(conn: Conexion) -> list[DictRow]:
    cur = await conn.execute(
        "select t.entidad_tipo, count(e.id) as total, "
        "count(e.id) filter (where e.estado = 'pendiente') as pendientes, "
        "count(e.id) filter (where e.estado = 'aceptada') as aceptadas, "
        "count(e.id) filter (where e.estado = 'corregida') as corregidas, "
        "count(e.id) filter (where e.estado = 'descartada') as descartadas, "
        "round(100.0 * count(e.id) filter (where e.estado = 'aceptada') "
        "/ nullif(count(e.id) filter (where e.estado <> 'pendiente'), 0), 1) "
        "as porcentaje_sin_correccion, "
        "round(avg(c.n) filter (where e.estado in ('aceptada', 'corregida')), 2) "
        "as promedio_campos_corregidos "
        "from (values ('actividad'), ('registro_tiempo'), ('meta')) "
        "as t (entidad_tipo) "
        "left join extraccion as e on e.entidad_tipo = t.entidad_tipo "
        "left join lateral ("
        "select count(*) as n from correccion_campo as cc "
        "where cc.extraccion_id = e.id) as c on true "
        "group by t.entidad_tipo order by t.entidad_tipo"
    )
    return await cur.fetchall()


async def modalidad_propuesta(conn: Conexion, captura_id: UUID) -> str | None:
    cur = await conn.execute(
        "select propuesta->>'modalidad' as modalidad from extraccion where id = %s",
        (captura_id,),
    )
    fila = await cur.fetchone()
    if fila is None:
        return None
    valor: str | None = fila["modalidad"]
    return valor
