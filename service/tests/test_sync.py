"""P2 verification: /sync + /jobs/{id} + /footage contracts (docs/api.md)."""

from fastapi.testclient import TestClient

from tempo_service import registry
from tempo_service.app import create_app


def _payload():
    return {
        "footages": [
            {
                "path": "C:\\v\\a.mp4",
                "size": 100,
                "mtime_ns": 1000,
                "item_id": 42,
                "frame_rate": 25.0,
            }
        ]
    }


def test_sync_round_trip(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    client = TestClient(create_app())

    r1 = client.post("/sync", json=_payload())
    assert r1.status_code == 200
    body = r1.json()
    assert len(body["added"]) == 1 and not body["unchanged"]
    assert len(body["jobs"]) == 1

    r2 = client.post("/sync", json=_payload())
    assert r2.json()["unchanged"] == body["added"]
    assert r2.json()["jobs"] == []

    job_id = body["jobs"][0]
    r3 = client.get(f"/jobs/{job_id}")
    assert r3.status_code == 200
    assert r3.json()["job_id"] == job_id
    assert len(r3.json()["stages"]) == 10  # §3.2 stage list (upload + 9)

    assert client.get("/jobs/nope").status_code == 404

    r4 = client.get("/footage")
    assert r4.status_code == 200
    assert r4.json()[0]["footage_key"] == body["added"][0]
