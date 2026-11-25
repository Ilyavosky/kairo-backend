import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.core import limites
from app.core.config import get_settings
from app.core.errors import ErrorApi
from app.main import create_app
from tests.doble_extractor import ExtractorFalso, actividad, usar_extractor
from tests.doble_redactor import RedactorFalso, usar_redactor
from tests.doble_telegram import (
    SECRETO_WEBHOOK,
    TelegramFalso,
    enviar,
    mensaje,
    usar_telegram,
    vincular,
)
from tests.helpers import PASSWORD, Sesion, crear_sesion


@pytest.fixture(autouse=True)
def limpiar() -> Iterator[None]:
    limites.reiniciar()
    yield
    limites.reiniciar()
    get_settings.cache_clear()


def test_permite_hasta_el_maximo_y_rechaza_el_siguiente() -> None:
    for _ in range(3):
        limites.verificar("prueba", "a", 3)
    with pytest.raises(ErrorApi) as error:
        limites.verificar("prueba", "a", 3)
    assert error.value.status_code == 429
    assert error.value.codigo == "demasiadas_peticiones"
    assert error.value.headers is not None
    assert int(error.value.headers["Retry-After"]) >= 1


def test_las_claves_y_los_nombres_son_independientes() -> None:
    limites.verificar("prueba", "a", 1)
    limites.verificar("prueba", "b", 1)
    limites.verificar("otra", "a", 1)
    with pytest.raises(ErrorApi):
        limites.verificar("prueba", "a", 1)


def test_la_ventana_se_libera_con_el_tiempo(monkeypatch: pytest.MonkeyPatch) -> None:
    reloj = [1000.0]
    monkeypatch.setattr("app.core.limites.time.monotonic", lambda: reloj[0])
    limites.verificar("prueba", "a", 1)
    with pytest.raises(ErrorApi):
        limites.verificar("prueba", "a", 1)
    reloj[0] += limites.VENTANA_S + 1
    limites.verificar("prueba", "a", 1)


def test_un_maximo_de_cero_desactiva_el_limite() -> None:
    for _ in range(50):
        limites.verificar("prueba", "a", 0)


def test_se_puede_desactivar_por_configuracion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIMITES_ACTIVOS", "false")
    get_settings.cache_clear()
    for _ in range(50):
        limites.verificar("prueba", "a", 1)


def test_limpia_las_cubetas_vencidas(monkeypatch: pytest.MonkeyPatch) -> None:
    reloj = [0.0]
    monkeypatch.setattr("app.core.limites.time.monotonic", lambda: reloj[0])
    monkeypatch.setattr(limites, "LIMPIEZA_CADA", 5)
    for i in range(5):
        limites.verificar("prueba", str(i), 1)
    reloj[0] += limites.VENTANA_S + 1
    limites.verificar("prueba", "nueva", 1)
    assert list(limites._cubetas) == ["prueba:nueva"]


@pytest.fixture
def limitado(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DB_ROLE", "kairo_app")
    monkeypatch.setenv("LIMITES_ACTIVOS", "true")
    monkeypatch.setenv("LIMITE_LOGIN_POR_MIN", "3")
    monkeypatch.setenv("LIMITE_CAPTURAS_POR_MIN", "2")
    monkeypatch.setenv("LIMITE_RESUMEN_POR_MIN", "2")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRETO_WEBHOOK)
    get_settings.cache_clear()
    limites.reiniciar()
    with TestClient(create_app()) as client:
        yield client


def login(client: TestClient, email: str, password: str = PASSWORD) -> int:
    respuesta = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    codigo: int = respuesta.status_code
    return codigo


def test_el_login_se_limita_por_correo(limitado: TestClient) -> None:
    ana = crear_sesion(limitado)
    limites.reiniciar()
    assert [login(limitado, ana.email) for _ in range(3)] == [200, 200, 200]
    bloqueado = limitado.post(
        "/api/v1/auth/login", json={"email": ana.email, "password": PASSWORD}
    )
    assert bloqueado.status_code == 429
    assert bloqueado.json()["codigo"] == "demasiadas_peticiones"
    assert int(bloqueado.headers["Retry-After"]) >= 1


def test_los_intentos_fallidos_tambien_cuentan(limitado: TestClient) -> None:
    ana = crear_sesion(limitado)
    limites.reiniciar()
    assert [login(limitado, ana.email, "incorrecta") for _ in range(3)] == [401] * 3
    assert login(limitado, ana.email) == 429


def test_otro_correo_no_se_ve_afectado(limitado: TestClient) -> None:
    ana = crear_sesion(limitado)
    beto = crear_sesion(limitado)
    limites.reiniciar()
    for _ in range(3):
        login(limitado, ana.email)
    assert login(limitado, ana.email) == 429
    assert login(limitado, beto.email) == 200


def test_el_login_tambien_se_limita_por_origen(limitado: TestClient) -> None:
    codigos = [login(limitado, f"{random.random()}@inexistente.mx") for _ in range(10)]
    assert codigos[:9] == [401] * 9
    assert codigos[9] == 429


def test_las_capturas_se_limitan_por_usuario(
    limitado: TestClient,
) -> None:
    ana = crear_sesion(limitado)
    beto = crear_sesion(limitado)
    usar_extractor(limitado, ExtractorFalso(actividad()))

    def capturar(sesion: Sesion) -> int:
        codigo: int = limitado.post(
            "/api/v1/capturas",
            json={"texto": "entregar reporte"},
            headers=sesion.headers,
        ).status_code
        return codigo

    assert [capturar(ana), capturar(ana)] == [201, 201]
    assert capturar(ana) == 429
    assert capturar(beto) == 201


def test_el_resumen_se_limita_por_usuario(limitado: TestClient) -> None:
    ana = crear_sesion(limitado)
    usar_redactor(limitado, RedactorFalso("Sin novedades."))

    def pedir() -> Response:
        respuesta: Response = limitado.get(
            "/api/v1/reportes/resumen", headers=ana.headers
        )
        return respuesta

    assert [pedir().status_code, pedir().status_code] == [200, 200]
    assert pedir().status_code == 429


def test_el_bot_tambien_respeta_el_limite_de_capturas(limitado: TestClient) -> None:
    ana = crear_sesion(limitado)
    telegram = TelegramFalso()
    usar_telegram(limitado, telegram)
    usar_extractor(limitado, ExtractorFalso(actividad()))
    tid = random.randint(10**9, 10**10)
    vincular(limitado, ana, telegram, tid)
    for _ in range(3):
        assert enviar(limitado, mensaje(tid, "entregar reporte")) == 200
    assert "Demasiados" in telegram.textos(tid)[-1]
