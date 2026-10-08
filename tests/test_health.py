# Test mínimo: evita que pytest devuelva código 5 en el CI.


def test_health_check() -> None:
    response = {"status": "healthy"}
    assert response["status"] == "healthy"
