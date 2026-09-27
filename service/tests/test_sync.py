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
    # §3.2: `upload` + the engine's stages (none known until the engine is probed)
    assert r3.json()["stages"][0]["name"] == "upload"

    assert client.get("/jobs/nope").status_code == 404

    r4 = client.get("/footage")
    assert r4.status_code == 200
    assert r4.json()[0]["footage_key"] == body["added"][0]


def _hold_payload(size, mtime, path="C:\\v\\hold.mp4"):
    return {
        "footages": [
            {
                "path": path,
                "size": size,
                "mtime_ns": mtime,
                "item_id": 7,
                "frame_rate": 25.0,
            }
        ]
    }


def test_sync_holds_bad_stats_and_dedups_jobs(tmp_path, monkeypatch):
    """Reopen race end-to-end: unreadable stats hold (no job, no entry),
    drift needs two sightings, and confirmation reuses the live job instead
    of minting a duplicate full pipeline run."""
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    client = TestClient(create_app())

    r0 = client.post("/sync", json=_hold_payload(-1, 0))
    assert r0.status_code == 200
    assert r0.json()["pending"] and r0.json()["jobs"] == []

    r1 = client.post("/sync", json=_hold_payload(100, 1000))
    key = r1.json()["added"][0]
    job_a = r1.json()["jobs"][0]  # stays queued: no handler in tests

    r2 = client.post("/sync", json=_hold_payload(200, 2000))
    assert r2.json()["jobs"] == [] and not r2.json()["changed"]

    r3 = client.post("/sync", json=_hold_payload(200, 2000))
    assert r3.json()["changed"] == [key]
    assert r3.json()["jobs"] == [job_a]  # dedup: same live job, no duplicate


def test_retry_reuses_live_job_and_cancel_drops_queued(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    client = TestClient(create_app())

    r1 = client.post("/sync", json=_hold_payload(100, 1000, "C:\\v\\rc.mp4"))
    key = r1.json()["added"][0]
    job_a = r1.json()["jobs"][0]

    rr = client.post(f"/footage/{key}/retry")
    assert rr.json()["job_id"] == job_a  # idempotent while active

    c1 = client.post(f"/jobs/{job_a}/cancel")
    assert c1.status_code == 200 and c1.json()["state"] == "cancelled"
    assert client.get(f"/jobs/{job_a}").json()["state"] == "cancelled"

    c2 = client.post(f"/jobs/{job_a}/cancel")
    assert c2.status_code == 409
    assert client.post("/jobs/job_nope/cancel").status_code == 404

    rr2 = client.post(f"/footage/{key}/retry")
    assert rr2.json()["job_id"] != job_a  # terminal: fresh job allowed
