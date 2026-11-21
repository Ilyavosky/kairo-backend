from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.helpers import (
    Sesion,
    categoria_id,
    categoria_propia,
    ejecutar_como_administrador,
)

URL = "/api/v1/metas"
REGISTROS = "/api/v1/registros-tiempo"


def crear(client: TestClient, sesion: Sesion, **extra: object) -> dict[str, object]:
    cuerpo = {
        "categoria_id": categoria_id(client, sesion, "Estudio"),
        "tipo": "tiempo_acumulado",
        "periodo": "semana",
        "objetivo": 100,
    }
    respuesta = client.post(URL, json={**cuerpo, **extra}, headers=sesion.headers)
    assert respuesta.status_code == 201, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def registrar(
    client: TestClient, sesion: Sesion, categoria: str, inicio: datetime, minutos: int
) -> None:
    respuesta = client.post(
        REGISTROS,
        json={
            "categoria_id": categoria,
            "inicio": inicio.isoformat(),
            "fin": (inicio + timedelta(minutes=minutos)).isoformat(),
        },
        headers=sesion.headers,
    )
    assert respuesta.status_code == 201, respuesta.text


def progreso(client: TestClient, sesion: Sesion, meta: object) -> dict[str, object]:
    respuesta = client.get(f"{URL}/{meta}/progreso", headers=sesion.headers)
    assert respuesta.status_code == 200, respuesta.text
    resultado: dict[str, object] = respuesta.json()
    return resultado


def inicio_del_periodo(avance: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(avance["periodo_desde"]))


def test_crear_meta_usa_valores_por_defecto(client: TestClient, ana: Sesion) -> None:
    meta = crear(client, ana)
    assert meta["activa"] is True
    assert meta["vigente_hasta"] is None
    assert meta["vigente_desde"] is not None
    assert [m["id"] for m in client.get(URL, headers=ana.headers).json()] == [
        meta["id"]
    ]


def test_meta_activa_repetida_responde_409_hasta_darla_de_baja(
    client: TestClient, ana: Sesion
) -> None:
    meta = crear(client, ana)
    repetida = client.post(
        URL,
        json={
            "categoria_id": meta["categoria_id"],
            "tipo": "tiempo_acumulado",
            "periodo": "semana",
            "objetivo": 50,
        },
        headers=ana.headers,
    )
    assert repetida.status_code == 409
    baja = client.patch(
        f"{URL}/{meta['id']}", json={"activa": False}, headers=ana.headers
    )
    assert baja.status_code == 200
    crear(client, ana, objetivo=50)
    activas = client.get(URL, params={"activa": True}, headers=ana.headers).json()
    assert len(activas) == 1


def test_metas_de_distinto_tipo_o_periodo_para_la_misma_categoria_conviven(
    client: TestClient, ana: Sesion
) -> None:
    crear(client, ana)
    crear(client, ana, tipo="numero_eventos")
    crear(client, ana, periodo="dia")


def test_objetivo_invalido_responde_422(client: TestClient, ana: Sesion) -> None:
    for objetivo in (0, -5):
        respuesta = client.post(
            URL,
            json={
                "categoria_id": categoria_id(client, ana),
                "tipo": "tiempo_acumulado",
                "periodo": "dia",
                "objetivo": objetivo,
            },
            headers=ana.headers,
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "validacion"


def test_tipo_o_periodo_desconocidos_responden_422(
    client: TestClient, ana: Sesion
) -> None:
    for cambio in ({"tipo": "tope"}, {"periodo": "anio"}):
        respuesta = client.post(
            URL,
            json={
                "categoria_id": categoria_id(client, ana),
                "tipo": "tiempo_acumulado",
                "periodo": "dia",
                "objetivo": 10,
                **cambio,
            },
            headers=ana.headers,
        )
        assert respuesta.status_code == 422


def test_vigencia_invertida_responde_422(client: TestClient, ana: Sesion) -> None:
    respuesta = client.post(
        URL,
        json={
            "categoria_id": categoria_id(client, ana),
            "tipo": "tiempo_acumulado",
            "periodo": "mes",
            "objetivo": 10,
            "vigente_desde": "2026-12-01",
            "vigente_hasta": "2026-11-01",
        },
        headers=ana.headers,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "restriccion_violada"


def test_categoria_inexistente_o_propia_de_otro_usuario_responde_422(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    secreta = categoria_propia(client, ana)
    for categoria in (str(uuid4()), secreta):
        respuesta = client.post(
            URL,
            json={
                "categoria_id": categoria,
                "tipo": "tiempo_acumulado",
                "periodo": "dia",
                "objetivo": 10,
            },
            headers=beto.headers,
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "referencia_invalida"


def test_patch_cambia_objetivo_y_vigencia(client: TestClient, ana: Sesion) -> None:
    meta = crear(client, ana)
    url = f"{URL}/{meta['id']}"
    cambio = client.patch(
        url,
        json={"objetivo": 240, "vigente_hasta": "2027-06-30"},
        headers=ana.headers,
    )
    assert cambio.status_code == 200
    assert cambio.json()["objetivo"] == 240
    assert cambio.json()["vigente_hasta"] == "2027-06-30"
    sin_fin = client.patch(url, json={"vigente_hasta": None}, headers=ana.headers)
    assert sin_fin.json()["vigente_hasta"] is None


def test_patch_vacio_con_nulo_o_con_campo_no_editable_responde_422(
    client: TestClient, ana: Sesion
) -> None:
    url = f"{URL}/{crear(client, ana)['id']}"
    assert client.patch(url, json={}, headers=ana.headers).status_code == 422
    nulo = client.patch(url, json={"objetivo": None}, headers=ana.headers)
    assert nulo.status_code == 422
    assert nulo.json()["codigo"] == "campo_no_nulo"
    tipo = client.patch(url, json={"tipo": "numero_eventos"}, headers=ana.headers)
    assert tipo.status_code == 422
    assert tipo.json()["codigo"] == "validacion"


def test_progreso_sin_registros_es_cero(client: TestClient, ana: Sesion) -> None:
    avance = progreso(client, ana, crear(client, ana)["id"])
    assert avance["progreso"] == 0
    assert avance["cumplida"] is False
    assert avance["porcentaje"] == 0


def test_progreso_de_tiempo_suma_solo_la_categoria_y_el_periodo(
    client: TestClient, ana: Sesion
) -> None:
    estudio = categoria_id(client, ana, "Estudio")
    meta = crear(client, ana, objetivo=100)
    desde = inicio_del_periodo(progreso(client, ana, meta["id"]))
    registrar(client, ana, estudio, desde + timedelta(hours=1), 60)
    registrar(client, ana, estudio, desde + timedelta(hours=3), 30)
    registrar(client, ana, estudio, desde - timedelta(hours=3), 60)
    tarea = categoria_id(client, ana, "Tarea")
    registrar(client, ana, tarea, desde + timedelta(hours=1), 45)
    avance = progreso(client, ana, meta["id"])
    assert avance["progreso"] == 90
    assert avance["cumplida"] is False
    assert avance["porcentaje"] == 90
    registrar(client, ana, estudio, desde + timedelta(hours=5), 40)
    cumplida = progreso(client, ana, meta["id"])
    assert cumplida["progreso"] == 130
    assert cumplida["cumplida"] is True
    assert cumplida["porcentaje"] == 130


def test_progreso_de_numero_de_eventos_cuenta_registros(
    client: TestClient, ana: Sesion
) -> None:
    ejercicio = categoria_id(client, ana, "Ejercicio")
    meta = crear(
        client,
        ana,
        categoria_id=ejercicio,
        tipo="numero_eventos",
        periodo="dia",
        objetivo=2,
    )
    desde = inicio_del_periodo(progreso(client, ana, meta["id"]))
    registrar(client, ana, ejercicio, desde + timedelta(hours=1), 20)
    assert progreso(client, ana, meta["id"])["cumplida"] is False
    registrar(client, ana, ejercicio, desde + timedelta(hours=5), 90)
    avance = progreso(client, ana, meta["id"])
    assert avance["progreso"] == 2
    assert avance["cumplida"] is True


def test_la_ventana_del_periodo_respeta_la_zona_horaria_del_usuario(
    client: TestClient, ana: Sesion
) -> None:
    avance = progreso(client, ana, crear(client, ana, periodo="dia")["id"])
    desde = inicio_del_periodo(avance)
    hasta = datetime.fromisoformat(str(avance["periodo_hasta"]))
    assert hasta - desde == timedelta(days=1)
    local = desde.astimezone(zona_de(client, ana))
    assert (local.hour, local.minute, local.second) == (0, 0, 0)


def zona_de(client: TestClient, sesion: Sesion) -> ZoneInfo:
    yo = client.get("/api/v1/auth/yo", headers=sesion.headers).json()
    return ZoneInfo(yo["zona_horaria"])


def test_metas_sin_token_responden_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.get(f"{URL}/historial").status_code == 401


def test_un_usuario_no_ve_ni_edita_metas_ajenas(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    meta = crear(client, ana)
    url = f"{URL}/{meta['id']}"
    assert client.get(URL, headers=beto.headers).json() == []
    assert client.get(url, headers=beto.headers).status_code == 404
    assert client.get(f"{url}/progreso", headers=beto.headers).status_code == 404
    baja = client.patch(url, json={"activa": False}, headers=beto.headers)
    assert baja.status_code == 404


def test_historial_lista_las_evaluaciones_propias(
    client: TestClient, ana: Sesion, beto: Sesion
) -> None:
    meta = crear(client, ana)
    otra = crear(client, ana, periodo="mes")
    for meta_id, semana, valor in ((meta["id"], 1, 120), (meta["id"], 2, 40)):
        ejecutar_como_administrador(
            "insert into evaluacion_meta (meta_id, usuario_id, periodo_desde, "
            "periodo_hasta, objetivo, valor_logrado, cumplida) "
            "values (%s, %s, %s, %s, 100, %s, %s)",
            (
                meta_id,
                ana.id,
                datetime.fromisoformat(f"2026-11-0{semana}T00:00:00-06:00"),
                datetime.fromisoformat(f"2026-11-0{semana}T23:59:00-06:00"),
                valor,
                valor >= 100,
            ),
        )
    todas = client.get(f"{URL}/historial", headers=ana.headers).json()
    assert [e["valor_logrado"] for e in todas] == [40, 120]
    assert [e["cumplida"] for e in todas] == [False, True]
    de_la_otra = client.get(
        f"{URL}/historial", params={"meta_id": otra["id"]}, headers=ana.headers
    )
    assert de_la_otra.json() == []
    assert client.get(f"{URL}/historial", headers=beto.headers).json() == []
