from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_safe_defaults() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["trading_enabled"] is False

