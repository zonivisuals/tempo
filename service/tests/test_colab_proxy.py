"""P9-minimal verification: Colab proxy contracts (docs/api.md, ADR-0002/0003).

- /health includes colab {reachable, gpu} (False when unconfigured).
- /sync includes uploads (empty when Colab unconfigured).
- /footage entries carry deterministic drive_path tempo/<key>/<basename>.
- /search proxies to Colab when configured: unreachable tunnel ->
  502 COLAB_UNREACHABLE (never hangs, never downloads).
- POST /drive-auth honest stub (501 DRIVE_NOT_CONFIGURED until uploader lands).
"""

from fastapi.testclient import TestClient

from tempo_service import registry
from tempo_service.drive import drive_path_for


def _client(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "colab_url", "")
    monkeypatch.setattr(app_module.settings, "colab_token", "")
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    return TestClient(create_app())


def create_app():
    from tempo_service.app import create_app as _make

    return _make()


def test_health_includes_colab(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["colab"] == {"reachable": False, "gpu": False}


def test_sync_includes_uploads_and_drive_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {"footages": [{"path": "C:\\v\\a.mp4", "size": 1, "mtime_ns": 2, "item_id": 3}]}
    body = client.post("/sync", json=payload).json()
    assert "uploads" in body
    assert body["uploads"] == []  # no Colab URL -> no upload handoff yet
    footage = client.get("/footage").json()
    assert footage[0]["drive_path"] == "tempo/" + footage[0]["footage_key"] + "/a.mp4"


def test_drive_path_deterministic():
    assert drive_path_for("a1b2", "C:\\v\\clip.mp4") == "tempo/a1b2/clip.mp4"
    assert drive_path_for("k", "/x/y.mov") == "tempo/k/y.mov"


def test_search_proxies_colab_unreachable(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "colab_url", "http://127.0.0.1:9")
    monkeypatch.setattr(app_module.settings, "colab_token", "t")
    monkeypatch.setattr(app_module.settings, "colab_timeout_s", 1.0)
    client = TestClient(app_module.create_app())
    r = client.get("/search", params={"q": "van"})
    assert r.status_code in (502, 504)
    assert r.json()["error"]["code"] in ("COLAB_UNREACHABLE", "COLAB_TIMEOUT")


def test_host_source_allowlist(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/host/host.jsx")
    assert r.status_code == 200
    assert "tempoListFootage" in r.text
    assert "no-store" in r.headers.get("cache-control", "")
    assert client.get("/host/json2.jsx").status_code == 200
    assert client.get("/host/evil.jsx").status_code == 404
    assert client.get("/host/app.jsx").status_code == 404


def test_search_backfills_empty_source_path(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    import tempo_service.colab as colab_module
    from tempo_service import registry as reg

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "colab_url", "https://x.ngrok.app")
    monkeypatch.setattr(app_module.settings, "colab_token", "t")
    reg.save_registry(
        {"k9": {"footage_key": "k9", "path": "C:\\v\\k9.mp4", "drive_path": "tempo/k9/k9.mp4",
                "size": 1, "mtime_ns": 1, "format_version": 1, "state": "ready",
                "shot_count": 1, "duration_s": 2.0, "indexed_at": None}}
    )
    body = {"query": "q", "took_ms": 5, "results": [
        {"footage_key": "k9", "shot_id": 0, "source_path": "", "start_s": 0.5, "end_s": 1.5,
         "score": 0.9, "winning_key": "caption",
         "raw_cos": {"visual": 0.1, "dialogue": 0.2, "caption": 0.3},
         "contributions": {"dense": 0.2, "bm25": 0.2, "anchor": 0.0, "entity_boost": 0.0},
         "transcript": "t", "caption": "c", "entities": []},
        {"footage_key": "k9", "shot_id": 1, "source_path": "C:\\keep.mp4", "start_s": 2.0,
         "end_s": 3.0, "score": 0.5, "winning_key": "visual",
         "raw_cos": {"visual": 0.4, "dialogue": 0.1, "caption": 0.1},
         "contributions": {"dense": 0.3, "bm25": 0.1, "anchor": 0.0, "entity_boost": 0.0},
         "transcript": "t2", "caption": "c2", "entities": []},
    ]}
    monkeypatch.setattr(colab_module, "search", lambda *a, **k: (True, 200, body, None))

    from fastapi.testclient import TestClient

    client = TestClient(app_module.create_app())
    r = client.get("/search", params={"q": "q"})
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["source_path"] == "C:\\v\\k9.mp4"  # backfilled from registry
    assert res[1]["source_path"] == "C:\\keep.mp4"  # non-empty left untouched


def test_drive_auth_stub(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/drive-auth", json={"code": "x"})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "DRIVE_NOT_CONFIGURED"


def test_colab_url_setter_and_thumb_fallback(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    import tempo_service.colab as colab_module

    client = _client(tmp_path, monkeypatch)
    r = client.post("/colab-url", json={"url": "not-a-url"})
    assert r.status_code == 400
    r = client.post("/colab-url", json={"url": "https://abc.ngrok-free.app"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Local thumb missing + Colab unreachable -> 404 (not a hang).
    monkeypatch.setattr(colab_module, "thumb_bytes", lambda *a, **k: (False, None, "COLAB_UNREACHABLE"))
    assert client.get("/thumb/a1b2/0.jpg").status_code == 404
    # Colab serves bytes -> proxied + cached locally.
    monkeypatch.setattr(colab_module, "thumb_bytes", lambda *a, **k: (True, b"\xff\xd8\xff\xd9", None))
    r = client.get("/thumb/a1b2/0.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert (tmp_path / "footage" / "a1b2" / "thumbs" / "shot_0.jpg").is_file()


def test_proxy_handoff_marks_ready(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    import tempo_service.colab as colab_module
    from tempo_service import jobs as jobs_module
    from tempo_service import registry as reg

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "colab_url", "https://x.ngrok.app")
    monkeypatch.setattr(app_module.settings, "colab_token", "t")
    monkeypatch.setattr(app_module.settings, "colab_timeout_s", 2.0)

    registry = {
        "k1": {"footage_key": "k1", "path": "C:\\v\\a.mp4", "drive_path": "tempo/k1/a.mp4",
               "size": 1, "mtime_ns": 1, "format_version": 1, "state": "indexing",
               "shot_count": 0, "duration_s": 0.0, "indexed_at": None}
    }
    reg.save_registry(registry)
    monkeypatch.setattr(
        colab_module, "index",
        lambda *a, **k: (True, 200, {"job_id": "cj1", "footage_key": "k1"}, None),
    )
    calls = {"n": 0}

    def fake_poll(*a, **k):
        calls["n"] += 1
        return (True, 200, {"job_id": "cj1", "state": "done", "shot_count": 7,
                            "duration_s": 12.5, "stages": []}, None)

    monkeypatch.setattr(colab_module, "job_status", fake_poll)
    monkeypatch.setattr("tempo_service.proxy.time.sleep", lambda s: None)

    from tempo_service.proxy import handle

    job = jobs_module.Job(job_id="job_x", footage_key="k1")
    progressed = []
    handle(job, lambda st, d, t: progressed.append(st))
    assert calls["n"] >= 1
    assert "upload" in progressed
    saved = reg.load_registry()
    assert saved["k1"]["state"] == "ready"
    assert saved["k1"]["shot_count"] == 7


def test_proxy_failure_marks_entry_error_and_retry(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    import tempo_service.colab as colab_module
    from tempo_service import jobs as jobs_module
    from tempo_service import registry as reg

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "colab_url", "https://x.ngrok.app")
    monkeypatch.setattr(app_module.settings, "colab_token", "t")
    reg.save_registry(
        {"k2": {"footage_key": "k2", "path": "C:\\v\\b.mp4", "drive_path": "tempo/k2/b.mp4",
                "size": 1, "mtime_ns": 1, "format_version": 1, "state": "indexing",
                "shot_count": 0, "duration_s": 0.0, "indexed_at": None}}
    )
    monkeypatch.setattr(
        colab_module, "index",
        lambda *a, **k: (True, 200, {"job_id": "cj9", "footage_key": "k2"}, None),
    )
    monkeypatch.setattr(
        colab_module, "job_status",
        lambda *a, **k: (True, 200, {"job_id": "cj9", "state": "error",
                                     "error": "footage not on Drive: tempo/k2/b.mp4",
                                     "stages": []}, None),
    )
    monkeypatch.setattr("tempo_service.proxy.time.sleep", lambda s: None)

    from tempo_service.proxy import handle

    job = jobs_module.Job(job_id="job_err", footage_key="k2")
    jobs_module.jobs._jobs[job.job_id] = job
    try:
        handle(job, lambda st, d, t: None)
        raise AssertionError("handle should raise")
    except RuntimeError as exc:
        assert "not on Drive" in str(exc)
        assert str(exc).count("Drive/tempo/k2/b.mp4") == 1  # single hint, not doubled
    saved = reg.load_registry()
    assert saved["k2"]["state"] == "error"
    assert "not on Drive" in saved["k2"]["error"]

    from fastapi.testclient import TestClient

    client = TestClient(app_module.create_app())
    r = client.post("/jobs/job_err/retry")
    assert r.status_code == 200
    assert r.json()["footage_key"] == "k2"
    assert client.get("/jobs/" + r.json()["job_id"]).status_code == 200
    assert reg.load_registry()["k2"]["state"] == "indexing"
    assert client.post("/jobs/nope/retry").status_code == 404


def test_footage_retry_by_key(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    from tempo_service import registry as reg

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "colab_url", "")
    reg.save_registry(
        {"k3": {"footage_key": "k3", "path": "C:\\v\\c.mp4", "drive_path": "tempo/k3/c.mp4",
                "size": 1, "mtime_ns": 1, "format_version": 1, "state": "error",
                "error": "boom", "shot_count": 0, "duration_s": 0.0, "indexed_at": None}}
    )
    from fastapi.testclient import TestClient

    client = TestClient(app_module.create_app())
    r = client.post("/footage/k3/retry")
    assert r.status_code == 200
    assert r.json()["footage_key"] == "k3"
    saved = reg.load_registry()
    assert saved["k3"]["state"] == "indexing"
    assert "error" not in saved["k3"]
    assert client.get("/jobs/" + r.json()["job_id"]).status_code == 200
    assert client.post("/footage/nope/retry").status_code == 404
    assert client.post("/footage/../x/retry").status_code == 404
