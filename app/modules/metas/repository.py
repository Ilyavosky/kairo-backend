from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import Conexion
from app.core.sql import actualizar_por_id, columnas
from app.modules.metas.schemas import MetaIn

COLUMNAS = (
    "id",
    "categoria_id",
    "tipo",
    "periodo",
    "objetivo",
    "vigente_desde",
    "vigente_hasta",
    "activa",
    "creada_en",
)
ANULABLES = frozenset({"vigente_hasta"})
COLUMNAS_EVALUACION = (
    "id",
    "meta_id",
    "periodo_desde",
    "periodo_hasta",
    "objetivo",
    "valor_logrado",
    "cumplida",
    "evaluada_en",
)

PROGRESO = """
select
    m.id as meta_id,
    m.tipo,
    m.periodo,
    m.objetivo,
    v.desde as periodo_desde,
    v.hasta as periodo_hasta,
    case m.tipo
        when 'tiempo_acumulado' then coalesce(a.minutos, 0)
        else coalesce(a.sesiones, 0)
    end as progreso,
    case m.tipo
        when 'tiempo_acumulado' then coalesce(a.minutos, 0) >= m.objetivo
        else coalesce(a.sesiones, 0) >= m.objetivo
    end as cumplida
from meta as m
join usuario as u on u.id = m.usuario_id
cross join lateral (
    select
        l.inicio at time zone u.zona_horaria as desde,
        (
            l.inicio + case m.periodo
                when 'dia' then interval '1 day'
                when 'semana' then interval '1 week'
                else interval '1 month'
            end
        ) at time zone u.zona_horaria as hasta
    from (
        select date_trunc(
            case m.periodo
                when 'dia' then 'day'
                when 'semana' then 'week'
                else 'month'
            end,
            now() at time zone u.zona_horaria
        ) as inicio
    ) as l
) as v
left join lateral (
    select
        sum(extract(epoch from r.fin - r.inicio)) / 60 as minutos,
        count(*) as sesiones
    from registro_tiempo as r
    where r.categoria_id = m.categoria_id
        and r.inicio >= v.desde
        and r.inicio < v.hasta
) as a on true
where m.id = %s
"""


async def listar(
    conn: Conexion, activa: bool | None, categoria_id: UUID | None
) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from meta "
        "where (%(activa)s::boolean is null or activa = %(activa)s) "
        "and (%(categoria_id)s::uuid is null or categoria_id = %(categoria_id)s) "
        "order by creada_en desc, id"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(consulta, {"activa": activa, "categoria_id": categoria_id})
    return await cur.fetchall()


async def obtener(conn: Conexion, meta_id: UUID) -> DictRow | None:
    consulta = sql.SQL("select {} from meta where id = %s").format(columnas(COLUMNAS))
    cur = await conn.execute(consulta, (meta_id,))
    return await cur.fetchone()


async def crear(conn: Conexion, usuario_id: UUID, datos: MetaIn) -> DictRow:
    consulta = sql.SQL(
        "insert into meta (usuario_id, categoria_id, tipo, periodo, objetivo, "
        "vigente_desde, vigente_hasta) "
        "values (%(usuario_id)s, %(categoria_id)s, %(tipo)s, %(periodo)s, "
        "%(objetivo)s, "
        "coalesce(%(vigente_desde)s::date, (now() at time zone "
        "(select zona_horaria from usuario where id = %(usuario_id)s))::date), "
        "%(vigente_hasta)s) returning {}"
    ).format(columnas(COLUMNAS))
    cur = await conn.execute(
        consulta,
        {
            "usuario_id": usuario_id,
            "categoria_id": datos.categoria_id,
            "tipo": datos.tipo,
            "periodo": datos.periodo,
            "objetivo": datos.objetivo,
            "vigente_desde": datos.vigente_desde,
            "vigente_hasta": datos.vigente_hasta,
        },
    )
    fila = await cur.fetchone()
    assert fila is not None
    return fila


async def actualizar(
    conn: Conexion, meta_id: UUID, campos: dict[str, object]
) -> DictRow | None:
    return await actualizar_por_id(conn, "meta", meta_id, campos, ANULABLES, COLUMNAS)


async def progreso(conn: Conexion, meta_id: UUID) -> DictRow | None:
    cur = await conn.execute(PROGRESO, (meta_id,))
    return await cur.fetchone()


async def historial(
    conn: Conexion, meta_id: UUID | None, limite: int, desplazamiento: int
) -> list[DictRow]:
    consulta = sql.SQL(
        "select {} from evaluacion_meta "
        "where (%(meta_id)s::uuid is null or meta_id = %(meta_id)s) "
        "order by periodo_desde desc, id "
        "limit %(limite)s offset %(desplazamiento)s"
    ).format(columnas(COLUMNAS_EVALUACION))
    cur = await conn.execute(
        consulta,
        {"meta_id": meta_id, "limite": limite, "desplazamiento": desplazamiento},
    )
    return await cur.fetchall()
