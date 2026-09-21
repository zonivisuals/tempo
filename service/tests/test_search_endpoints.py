"""P4 verification: /search + /thumb endpoint contracts (docs/api.md).

- Empty corpus → 200 with [] (no model touched, no downloads ever).
- Non-empty corpus without cached CLIP weights → 503 MODEL_NOT_LOADED.
- /thumb serves bytes with cache headers; unknown key/shot → 404.
"""

from fastapi.testclient import TestClient

from tempo_service import registry
from tempo_service.app import create_app


def _client(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    return TestClient(create_app())


def test_search_empty_corpus_needs_no_model(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/search", params={"q": "vending machine"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "vending machine" and body["results"] == []
    assert isinstance(body["took_ms"], int)


def test_search_without_cached_weights_is_503(tmp_path, monkeypatch):
    import numpy as np

    client = _client(tmp_path, monkeypatch)
    root = tmp_path / "footage" / "a1b2"
    (root / "thumbs").mkdir(parents=True)
    shots = [
        {
            "shot_id": 0, "start_s": 0.0, "end_s": 1.0,
            "transcript": "hello", "caption": "a van",
            "ocr_text": "", "entities": [], "cluster_id": 0,
        }
    ]
    (root / "shots.json").write_text(__import__("json").dumps(shots))
    np.savez_compressed(
        root / "embeddings.npz",
        visual=np.zeros((1, 4), dtype=np.float32),
        dialogue=np.zeros((1, 4), dtype=np.float32),
        caption=np.zeros((1, 4), dtype=np.float32),
    )
    (root / "bm25.pkl").write_bytes(__import__("pickle").dumps(_FakeBM25()))
    registry.save_registry(
        {
            "a1b2": {
                "footage_key": "a1b2", "path": "C:\\v\\a.mp4",
                "size": 1, "mtime_ns": 1, "format_version": 1,
                "state": "ready", "shot_count": 1,
                "duration_s": 1.0, "indexed_at": None,
            }
        }
    )
    # Fresh CI env has no CLIP weights cached → must be 503, never a download.
    r = client.get("/search", params={"q": "van"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "MODEL_NOT_LOADED"


class _FakeBM25:
    def get_scores(self, tokens):
        return [1.0]


def test_thumb_serves_and_404s(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    d = tmp_path / "footage" / "a1b2" / "thumbs"
    d.mkdir(parents=True)
    (d / "shot_0.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    r = client.get("/thumb/a1b2/0.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "max-age=86400" in r.headers["cache-control"]
    assert client.get("/thumb/a1b2/7.jpg").status_code == 404
    assert client.get("/thumb/nope/0.jpg").status_code == 404
    assert client.get("/thumb/../x/0.jpg").status_code in (404, 422)
