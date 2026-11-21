from fastapi.testclient import TestClient


def test_health_responde_sin_tocar_la_base(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_db_consulta_la_base(client: TestClient) -> None:
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "db": "ok"}


def test_cors_permite_el_origen_configurado(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rechaza_origenes_no_configurados(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://otro-sitio.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
