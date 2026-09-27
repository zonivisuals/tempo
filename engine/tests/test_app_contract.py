"""Engine /v1 contract (docs/engine-api.md) with a fake pipeline and fixed query vectors."""

import hashlib
import io
import json
import tarfile
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tempo_engine import fingerprint, models, pipeline
from tempo_engine.app import Encoders, create_app
from tempo_engine.config import EngineSettings
from tempo_engine.index import TempoIndex

TOKEN = "t0k3n"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PROF = models.current_profile()
SIGNATURE = pipeline.current_signature(PROF)
DV, DT = 8, 6


def fake_index(root, cid, n=4):
    (root / "frames").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(len(cid))
    shots = []
    for i in range(n):
        rel = f"frames/k{i}.jpg"
        Image.new("RGB", (64, 36), (i * 40, 0, 0)).save(root / rel)
        shots.append({"shot_id": i, "scene_id": i, "start_time": i * 2.0, "end_time": i * 2.0 + 2.0,
                      "duration": 2.0, "keyframe_path": rel, "frame_paths": [rel],
                      "transcript": "we drive to akita", "dialogue_en": "we drive to akita at night",
                      "dialogue_src": "we drive to akita at night", "has_dialogue": True,
                      "entities": ["Akita"], "emotions": ["joy"], "ocr_text": "", "caption": "a road",
                      "caption_conf": 1.0, "cluster_id": 0, "is_cluster_rep": True})
    norm = lambda m: (m / np.linalg.norm(m, axis=1, keepdims=True)).astype(np.float32)  # noqa: E731
    arrays = {"V": norm(rng.normal(size=(n, DV))), "D": norm(rng.normal(size=(n, DT))),
              "D_mask": np.ones(n, bool), "C": norm(rng.normal(size=(n, DT)))}
    meta = {"content_id": cid, "signature": SIGNATURE, "fps": 25.0, "duration": n * 2.0, "n_shots": n}
    idx = TempoIndex(root, meta, shots, {"akita": "Akita"}, arrays)
    idx.write_thumbs(lambda d, t: None)
    idx.save()


def make_client(tmp_path, runner=None, **overrides):
    cfg = EngineSettings(data_root=tmp_path, token=TOKEN, preload_query_models=False, **overrides)
    calls = []

    def default_runner(cid, report):
        calls.append(cid)
        for name in pipeline.STAGES:
            report.progress(name, 1, 2)
            report.done(name)
        fake_index(tmp_path / "library" / cid, cid)
        return {"shot_count": 4, "duration_s": 8.0, "fps": 25.0}

    enc = Encoders(visual=lambda q: np.ones(DV, np.float32) / np.sqrt(DV),
                   text=lambda q: np.ones(DT, np.float32) / np.sqrt(DT),
                   ner=lambda texts: [["Akita"] if "akita" in t.lower() else [] for t in texts])
    app = create_app(cfg, runner=runner or default_runner, encoders=enc, prof=PROF)
    return TestClient(app), calls


def cid_of(data: bytes) -> str:
    """fingerprint.content_id for in-memory bytes (same algorithm, no file)."""
    h = hashlib.sha1(str(len(data)).encode())
    h.update(data[:fingerprint.CHUNK_BYTES])
    if len(data) > fingerprint.CHUNK_BYTES:
        h.update(data[-fingerprint.CHUNK_BYTES:])
    return h.hexdigest()[:fingerprint.ID_LENGTH]


def upload(client, data, chunk=5, name="clip.MP4"):
    cid = cid_of(data)
    for off in range(0, len(data), chunk):
        r = client.put(f"/v1/uploads/{cid}", params={"offset": off, "size": len(data), "name": name},
                       content=data[off:off + chunk], headers=AUTH)
        assert r.status_code == 200, r.text
    return cid, r.json()


def wait_job(client, job_id, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        body = client.get(f"/v1/jobs/{job_id}", headers=AUTH).json()
        if body["state"] in ("done", "error"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_health_is_public_and_names_stages(tmp_path):
    client, _ = make_client(tmp_path)
    body = client.get("/v1/health").json()
    assert body["stages"] == pipeline.STAGES and body["signature"] == SIGNATURE
    assert body["query_models"] == "ready" and body["status"] == "ok"


def test_auth_fails_closed(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/v1/library/" + "0" * 16).status_code == 401
    assert client.get("/v1/library/" + "0" * 16, headers={"Authorization": "Bearer nope"}).status_code == 401
    cfg = EngineSettings(data_root=tmp_path / "x", token="", preload_query_models=False)
    open_client = TestClient(create_app(cfg, prof=PROF))
    r = open_client.get("/v1/library/" + "0" * 16, headers={"Authorization": "Bearer "})
    assert r.status_code == 500 and r.json()["error"]["code"] == "NO_TOKEN"


def test_bad_content_id_is_not_found(tmp_path):
    client, _ = make_client(tmp_path)
    for cid in ("..%2F..%2Fetc", "ABCDEF0123456789", "short"):
        assert client.get(f"/v1/library/{cid}", headers=AUTH).status_code == 404


def test_resumable_upload_rejects_wrong_offset_and_verifies_content(tmp_path):
    client, _ = make_client(tmp_path)
    data = b"frame-bytes-" * 10
    cid, _ = upload(client, data, chunk=len(data))
    assert client.get(f"/v1/uploads/{cid}", headers=AUTH).json()["complete"] is True

    data2 = b"other-footage-" * 7
    cid2 = cid_of(data2)
    ok = client.put(f"/v1/uploads/{cid2}", params={"offset": 0, "size": len(data2)}, content=data2[:10],
                    headers=AUTH)
    assert ok.json() == {"content_id": cid2, "received": 10, "size": len(data2), "complete": False}
    bad = client.put(f"/v1/uploads/{cid2}", params={"offset": 0, "size": len(data2)}, content=data2[:10],
                     headers=AUTH)
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "OFFSET_MISMATCH"
    assert json.loads(bad.json()["error"]["message"]) == {"received": 10}
    assert client.get(f"/v1/library/{cid2}", headers=AUTH).json()["state"] == "partial"
    done = client.put(f"/v1/uploads/{cid2}", params={"offset": 10, "size": len(data2)}, content=data2[10:],
                      headers=AUTH)
    assert done.json()["complete"] is True

    wrong = "f" * 16
    r = client.put(f"/v1/uploads/{wrong}", params={"offset": 0, "size": 4}, content=b"abcd", headers=AUTH)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONTENT_MISMATCH"
    assert client.get(f"/v1/uploads/{wrong}", headers=AUTH).json()["received"] == 0


def test_chunk_limit(tmp_path):
    client, _ = make_client(tmp_path, max_chunk_mb=1)
    r = client.put("/v1/uploads/" + "a" * 16, params={"offset": 0, "size": 3 * 1024 * 1024},
                   content=b"\0" * (2 * 1024 * 1024), headers=AUTH)
    assert r.status_code == 413 and r.json()["error"]["code"] == "CHUNK_TOO_LARGE"


def test_index_requires_source_then_runs_and_is_reused(tmp_path):
    with make_client(tmp_path)[0] as client:
        cid = "0123456789abcdef"
        r = client.post("/v1/index", json={"content_id": cid}, headers=AUTH)
        assert r.status_code == 409 and r.json()["error"]["code"] == "SOURCE_MISSING"
        assert client.get(f"/v1/library/{cid}", headers=AUTH).json() == {
            "content_id": cid, "state": "missing", "needs_upload": True, "received": 0, "size": 0,
            "job_id": None, "shot_count": 0, "duration_s": 0.0, "fps": 0.0, "error": None}

        cid, _ = upload(client, b"some video bytes" * 3)
        assert client.get(f"/v1/library/{cid}", headers=AUTH).json()["state"] == "uploaded"
        job = client.post("/v1/index", json={"content_id": cid}, headers=AUTH).json()
        body = wait_job(client, job["job_id"])
        assert body["state"] == "done" and body["shot_count"] == 4
        assert [s["name"] for s in body["stages"]] == pipeline.STAGES
        assert all(s["state"] == "done" and s["done"] == s["total"] for s in body["stages"])

        entry = client.get(f"/v1/library/{cid}", headers=AUTH).json()
        assert entry["state"] == "ready" and entry["shot_count"] == 4 and entry["fps"] == 25.0
        # Raw purged after index (ADR-0006 retention); ready content never needs bytes again.
        assert entry["needs_upload"] is True and entry["received"] == 0
        again = client.post("/v1/index", json={"content_id": cid}, headers=AUTH).json()
        assert again == {"job_id": None, "state": "done"}


def test_submit_is_idempotent_while_live(tmp_path):
    gate = threading.Event()

    def slow_runner(cid, report):
        gate.wait(5)
        fake_index(tmp_path / "library" / cid, cid)
        return {"shot_count": 4}

    with make_client(tmp_path, runner=slow_runner)[0] as client:
        cid, _ = upload(client, b"x" * 40)
        a = client.post("/v1/index", json={"content_id": cid}, headers=AUTH).json()
        b = client.post("/v1/index", json={"content_id": cid}, headers=AUTH).json()
        assert a["job_id"] == b["job_id"]
        assert client.get(f"/v1/library/{cid}", headers=AUTH).json()["state"] == "indexing"
        gate.set()
        assert wait_job(client, a["job_id"])["state"] == "done"


def test_failed_job_reports_stage_and_library_error(tmp_path):
    def broken(cid, report):
        report.progress("shots", 0, 0)
        raise RuntimeError("decoder exploded")

    with make_client(tmp_path, runner=broken)[0] as client:
        cid, _ = upload(client, b"y" * 40)
        job = client.post("/v1/index", json={"content_id": cid}, headers=AUTH).json()
        body = wait_job(client, job["job_id"])
        assert body["state"] == "error" and "decoder exploded" in body["error"]
        assert body["stages"][0]["state"] == "error"
        entry = client.get(f"/v1/library/{cid}", headers=AUTH).json()
        assert entry["state"] == "error" and "decoder exploded" in entry["error"]


def test_restart_recovers_interrupted_jobs(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True)
    cid = "abcdefabcdefabcd"
    (tmp_path / "raw" / cid).mkdir(parents=True)
    (tmp_path / "raw" / cid / "source.mp4").write_bytes(b"z")
    stages = [{"name": n, "state": "done" if n == "shots" else "pending", "done": 0, "total": 0}
              for n in pipeline.STAGES]
    stages[1]["state"] = "running"
    (jobs_dir / "ejob_dead0001.json").write_text(json.dumps({
        "job_id": "ejob_dead0001", "content_id": cid, "state": "running", "stages": stages, "error": None,
        "shot_count": 0, "duration_s": 0.0, "fps": 0.0, "created_at": 1.0}))
    client, calls = make_client(tmp_path)
    with client:
        body = wait_job(client, "ejob_dead0001")
    assert body["state"] == "done" and calls == [cid]


def test_search_shape_and_thumbs(tmp_path):
    client, _ = make_client(tmp_path)
    for cid in ("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"):
        fake_index(tmp_path / "library" / cid, cid)
    body = client.get("/v1/search", params={"q": "road trip to akita", "top_k": 3}, headers=AUTH).json()
    assert body["entities"] == ["Akita"] and 0 < len(body["results"]) <= 3
    r = body["results"][0]
    assert set(r) == {"content_id", "shot_id", "scene_id", "start_s", "end_s", "score", "contributions",
                      "raw_cos", "transcript", "dialogue", "caption", "ocr", "entities", "emotions"}
    assert sum(r["contributions"].values()) == pytest.approx(r["score"], abs=1e-6)
    only_b = client.get("/v1/search", params={"q": "akita", "content_ids": "bbbbbbbbbbbbbbbb"},
                        headers=AUTH).json()
    assert {x["content_id"] for x in only_b["results"]} == {"bbbbbbbbbbbbbbbb"}

    t = client.get("/v1/library/aaaaaaaaaaaaaaaa/thumbs/1.jpg", headers=AUTH)
    assert t.status_code == 200 and t.headers["cache-control"] == "public, max-age=86400"
    assert client.get("/v1/library/aaaaaaaaaaaaaaaa/thumbs/99.jpg", headers=AUTH).status_code == 404
    tar = client.get("/v1/library/aaaaaaaaaaaaaaaa/thumbs.tar", headers=AUTH)
    with tarfile.open(fileobj=io.BytesIO(tar.content)) as tf:
        assert sorted(tf.getnames()) == ["0.jpg", "1.jpg", "2.jpg", "3.jpg"]


def test_search_empty_library_and_warming(tmp_path):
    client, _ = make_client(tmp_path)
    body = client.get("/v1/search", params={"q": "anything"}, headers=AUTH).json()
    assert body["results"] == [] and body["query"] == "anything"
    cfg = EngineSettings(data_root=tmp_path / "w", token=TOKEN, preload_query_models=True)
    warming = TestClient(create_app(cfg, runner=lambda c, r: {}, prof=PROF))
    r = warming.get("/v1/search", params={"q": "x"}, headers=AUTH)
    assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_WARMING"


def test_stale_signature_is_not_searched(tmp_path):
    client, _ = make_client(tmp_path)
    root = tmp_path / "library" / "cccccccccccccccc"
    fake_index(root, "cccccccccccccccc")
    payload = json.loads((root / "index.json").read_text())
    payload["meta"]["signature"] = "older"
    (root / "index.json").write_text(json.dumps(payload))
    assert client.get("/v1/library/cccccccccccccccc", headers=AUTH).json()["state"] == "stale"
    assert client.get("/v1/search", params={"q": "akita"}, headers=AUTH).json()["results"] == []


def test_in_memory_cid_matches_file_fingerprint(tmp_path):
    for data in (b"abc", b"" * (fingerprint.CHUNK_BYTES + 3)):
        path = tmp_path / "f.bin"
        path.write_bytes(data)
        assert cid_of(data) == fingerprint.content_id(path)
