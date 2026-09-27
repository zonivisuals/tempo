"""P1 verification: /health contract."""

from fastapi.testclient import TestClient

from tempo_service.app import create_app


def test_health_ok():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["backend"]["tunnel"] == "off"  # no Brev instance configured
    assert "models_loaded" not in body  # the sidecar holds no models (ADR-0008)
    assert isinstance(body["artifact_root"], str)
