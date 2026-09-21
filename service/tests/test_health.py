"""P1 verification: /health contract."""

from fastapi.testclient import TestClient

from tempo_service.app import create_app


def test_health_ok():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["models_loaded"], dict)
    assert isinstance(body["artifact_root"], str)
