"""Engine seam + handoff (ADR-0008, docs/api.md v2).

- Factory / engine_url: direct URL, Brev tunnel port, unconfigured -> None.
- HttpBackend error mapping against a real local HTTP server.
- /health, /sync, /footage, /search, /thumb against a fake provider.
- proxy.handle against an in-memory engine: library reuse, fresh + resumed
  uploads, offset resync, attach to a live engine job, errors, asleep waits,
  thumb sync-down (with hostile tar names rejected).
- Content id: sidecar and engine copies agree (AGENTS.md §8 cross-check).
"""

import importlib.util
import io
import json
import sys
import tarfile
import threading
import time
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tempo_service.backend_status as backend_status
from tempo_service import fingerprint
from tempo_service import jobs as jobs_module
from tempo_service import proxy as proxy_module
from tempo_service import registry as reg
from tempo_service.backends import ASLEEP, TIMEOUT, UNREACHABLE, BackendProvider, HttpBackend, Reply, get_provider
from tempo_service.config import Settings

ENGINE_FP = Path(__file__).resolve().parents[2] / "engine" / "tempo_engine" / "fingerprint.py"
STAGES = ["shots", "visual", "transcribe", "ocr", "captions", "text", "index"]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    for mod in (app_module, reg, proxy_module):
        monkeypatch.setattr(mod.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "backend_url", "http://engine.test")
    monkeypatch.setattr(app_module.settings, "brev_instance", "")
    monkeypatch.setattr(app_module.settings, "upload_chunk_mb", 1)
    monkeypatch.setattr(proxy_module, "time", SimpleNamespace(sleep=lambda s: None))
    with backend_status._lock:
        backend_status._status.update(backend_status.UNREACHABLE_STATUS)
    yield


def tar_of(names: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in names.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeEngine(BackendProvider):
    """In-memory engine speaking the /v1 semantics the handoff relies on."""

    def __init__(self, state="missing", received=0, job_state_seq=None, thumbs=None):
        self.state, self.received = state, received
        self.chunks: list[tuple[int, int]] = []
        self.submits = 0
        self.job_seq = list(job_state_seq or ["running", "done"])
        self.thumbs = thumbs if thumbs is not None else {"0.jpg": b"\xff\xd8a", "1.jpg": b"\xff\xd8b"}
        self.library_replies: list[Reply] = []
        self.mismatch_once_at: int | None = None

    def health(self):
        return {"reachable": True, "gpu": True, "signature": "sig", "stages": STAGES, "query_models": "ready"}

    def library(self, cid):
        if self.library_replies:
            return self.library_replies.pop(0)
        return Reply(True, 200, {"content_id": cid, "state": self.state, "received": self.received,
                                 "size": 0, "job_id": "ejob_live" if self.state == "indexing" else None,
                                 "needs_upload": self.state in ("missing", "partial"),
                                 "shot_count": 5, "duration_s": 9.0, "fps": 25.0})

    def upload_chunk(self, cid, offset, size, name, data):
        if self.mismatch_once_at is not None and offset == self.mismatch_once_at:
            self.mismatch_once_at = None
            return Reply(False, 409, code="OFFSET_MISMATCH", message=json.dumps({"received": self.received}))
        assert offset == self.received, (offset, self.received)
        self.chunks.append((offset, len(data)))
        self.received += len(data)
        return Reply(True, 200, {"content_id": cid, "received": self.received, "size": size,
                                 "complete": self.received == size})

    def submit_index(self, cid):
        self.submits += 1
        return Reply(True, 200, {"job_id": "ejob_new", "state": "queued"})

    def job_status(self, job_id):
        state = self.job_seq.pop(0) if len(self.job_seq) > 1 else self.job_seq[0]
        stages = [{"name": n, "state": "done" if state == "done" else ("running" if i == 0 else "pending"),
                   "done": 3, "total": 4} for i, n in enumerate(STAGES)]
        return Reply(True, 200, {"job_id": job_id, "content_id": "x", "state": state, "stages": stages,
                                 "error": "decoder exploded" if state == "error" else None,
                                 "shot_count": 5, "duration_s": 9.0, "fps": 25.0})

    def search(self, q, top_k, content_ids):
        raise AssertionError("not used")

    def thumb_bytes(self, cid, shot_id):
        return Reply(False, 404, code="NOT_FOUND")

    def thumbs_tar(self, cid):
        return Reply(True, 200, tar_of(self.thumbs))


def seed_footage(tmp_path, size=2_500_000, key="k1"):
    src = tmp_path / f"{key}.mp4"
    src.write_bytes(bytes(range(256)) * (size // 256) + b"\0" * (size % 256))
    reg.save_registry({key: {"footage_key": key, "path": str(src), "content_id": "", "size": size,
                             "mtime_ns": 1, "format_version": 2, "state": "indexing", "shot_count": 0,
                             "duration_s": 0.0, "indexed_at": None, "reused": False}})
    return src


def run_handle(engine, monkeypatch, key="k1"):
    """Drive the handoff the way the worker does: a real Job in the manager, and
    the same JobHandle the handler is given in production."""
    monkeypatch.setattr(proxy_module, "get_provider", lambda s: engine)
    mgr = jobs_module.jobs
    job = jobs_module.Job(job_id="job_" + key, footage_key=key, stage_names=["upload", *STAGES])
    with mgr._lock:
        mgr._jobs[job.job_id] = job
    handle = jobs_module.JobHandle(mgr, job.job_id)
    ticks = []
    real_progress = handle.progress
    handle.progress = lambda st, d, t: (ticks.append((st, d, t)), real_progress(st, d, t))
    proxy_module.handle(handle)
    return job, ticks


# --- factory ------------------------------------------------------------------

def test_engine_url_and_factory():
    assert get_provider(Settings(backend_url="", brev_instance="")) is None
    s = Settings(backend_url="", brev_instance="tempo-l4-instance", tunnel_local_port=9911)
    assert s.engine_url == "http://127.0.0.1:9911"
    assert isinstance(get_provider(s), HttpBackend)
    assert Settings(backend_url="http://10.0.0.2:8900", brev_instance="x").engine_url == "http://10.0.0.2:8900"


# --- HttpBackend against a real server ------------------------------------------

class _Stub(BaseHTTPRequestHandler):
    routes: dict = {}

    def _reply(self):
        status, body, delay = self.routes.get(self.path.split("?")[0], (404, {}, 0))
        time.sleep(delay)
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = _reply

    def log_message(self, *a):
        pass


@pytest.fixture
def stub_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_http_backend_error_mapping(stub_server):
    cid = "0123456789abcdef"
    _Stub.routes = {
        "/v1/health": (200, {"gpu": True, "signature": "s1", "stages": STAGES, "query_models": "ready"}, 0),
        f"/v1/library/{cid}": (503, {"error": {"code": "MODEL_WARMING", "message": "loading"}}, 0),
        f"/v1/uploads/{cid}": (409, {"error": {"code": "OFFSET_MISMATCH", "message": '{"received": 7}'}}, 0),
        "/v1/index": (401, {"error": {"code": "UNAUTHORIZED", "message": "bad token"}}, 0),
        "/v1/jobs/slow": (200, {}, 1.5),
        f"/v1/library/{cid}/thumbs.tar": (200, b"TARBYTES", 0),
    }
    engine = HttpBackend(stub_server, "t", timeout_s=0.5)
    assert engine.health() == {"reachable": True, "gpu": True, "signature": "s1", "stages": STAGES,
                               "query_models": "ready"}
    assert engine.library(cid).code == ASLEEP
    up = engine.upload_chunk(cid, 0, 10, "a.mp4", b"x")
    assert up.code == "OFFSET_MISMATCH" and json.loads(up.message) == {"received": 7}
    assert up.transport_code == UNREACHABLE
    assert engine.submit_index(cid).code == UNREACHABLE  # rejected token never leaks as an app code
    assert engine.job_status("slow").code == TIMEOUT
    assert engine.thumbs_tar(cid).body == b"TARBYTES"
    down = HttpBackend("http://127.0.0.1:9", "t", timeout_s=0.5)
    assert down.library(cid).code in (UNREACHABLE, TIMEOUT)  # refused, or dropped (Windows)
    assert down.health()["reachable"] is False


# --- routes ------------------------------------------------------------------------

def _client():
    import tempo_service.app as app_module

    return TestClient(app_module.create_app())


def test_health_reports_engine_and_tunnel(monkeypatch):
    monkeypatch.setattr(backend_status, "get_provider", lambda s, t=None: FakeEngine())
    body = _client().get("/health").json()
    assert body["backend"] == {"reachable": True, "gpu": True, "tunnel": "off", "signature": "sig"}
    assert backend_status.stage_names("upload") == ["upload", *STAGES]


def test_health_serves_cache_without_probing(monkeypatch):
    with backend_status._lock:
        backend_status._status.update({"reachable": True, "gpu": True, "signature": "s",
                                      "stages": STAGES, "checked_at": time.monotonic()})

    def explode(*a, **k):
        raise AssertionError("cached health must not probe")

    monkeypatch.setattr(backend_status, "get_provider", explode)
    assert _client().get("/health").json()["backend"]["reachable"] is True


def test_the_last_known_stages_survive_an_unreachable_engine(monkeypatch):
    # A stopped instance should read as a transition, not as an empty step list.
    with backend_status._lock:
        backend_status._status.update({"reachable": True, "gpu": True, "signature": "s",
                                      "stages": STAGES, "checked_at": 1.0})
    monkeypatch.setattr(backend_status, "get_provider",
                        lambda s, t=None: dict(backend_status.UNREACHABLE_STATUS, reachable=False))
    assert backend_status.refresh()["stages"] == STAGES


def test_probe_never_raises(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("misconfigured")

    monkeypatch.setattr(backend_status, "get_provider", broken)
    assert backend_status._probe_once()["reachable"] is False


def test_removed_routes_are_gone():
    client = _client()
    assert client.post("/colab-url", json={"url": "https://x"}).status_code == 404
    assert client.post("/drive-auth", json={"code": "x"}).status_code == 404


def test_sync_hands_every_job_to_the_engine():
    client = _client()
    body = client.post("/sync", json={"footages": [
        {"path": "C:\\v\\a.mp4", "size": 1, "mtime_ns": 2, "item_id": 3}]}).json()
    assert body["uploads"] == body["jobs"] and len(body["jobs"]) == 1
    footage = client.get("/footage").json()[0]
    assert footage["content_id"] == "" and footage["reused"] is False and "drive_path" not in footage


def _ready_registry():
    reg.save_registry({
        "k1": {"footage_key": "k1", "path": "C:\\v\\a.mp4", "content_id": "aaaaaaaaaaaaaaaa", "state": "ready"},
        "k2": {"footage_key": "k2", "path": "C:\\v\\copy-of-a.mp4", "content_id": "aaaaaaaaaaaaaaaa",
               "state": "ready"},
        "k3": {"footage_key": "k3", "path": "C:\\v\\b.mp4", "content_id": "bbbbbbbbbbbbbbbb", "state": "ready"},
        "k4": {"footage_key": "k4", "path": "C:\\v\\c.mp4", "content_id": "", "state": "indexing"},
    })


def _engine_result(cid, shot_id):
    return {"content_id": cid, "shot_id": shot_id, "scene_id": shot_id, "start_s": 1.0, "end_s": 2.5,
            "score": 0.4, "contributions": {"visual": 0.2, "dialogue": 0.1, "caption": 0.05, "bm25": 0.05,
                                            "entity": 0.0, "anchor": 0.0},
            "raw_cos": {"visual": 0.1, "dialogue": None, "caption": 0.5}, "transcript": "t",
            "dialogue": "d", "caption": "c", "ocr": "", "entities": [], "emotions": []}


def test_search_maps_content_back_to_footage(monkeypatch):
    import tempo_service.app as app_module

    _ready_registry()
    seen = {}

    class Engine(FakeEngine):
        def search(self, q, top_k, content_ids):
            seen["ids"] = content_ids
            return Reply(True, 200, {"query": q, "took_ms": 3, "entities": ["Akita"], "results": [
                _engine_result("aaaaaaaaaaaaaaaa", 4), _engine_result("bbbbbbbbbbbbbbbb", 1),
                _engine_result("cccccccccccccccc", 2)]})

    monkeypatch.setattr(app_module, "get_provider", lambda s, t=None: Engine())
    client = _client()
    body = client.get("/search", params={"q": "akita"}).json()
    assert seen["ids"] == ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]  # ready contents, registry order, unique
    assert body["entities"] == ["Akita"]
    assert [(r["footage_key"], r["source_path"]) for r in body["results"]] == [
        ("k1", "C:\\v\\a.mp4"), ("k3", "C:\\v\\b.mp4")]  # unknown content dropped
    assert body["results"][0]["raw_cos"]["dialogue"] is None

    client.get("/search", params={"q": "akita", "footage_keys": "k2"})
    assert seen["ids"] == ["aaaaaaaaaaaaaaaa"]


def test_search_without_ready_footage_never_calls_engine(monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module, "get_provider", lambda *a: pytest.fail("engine called"))
    assert _client().get("/search", params={"q": "van"}).json()["results"] == []


def test_search_engine_unreachable_is_inline_error(monkeypatch):
    import tempo_service.app as app_module

    _ready_registry()
    monkeypatch.setattr(app_module.settings, "backend_url", "http://127.0.0.1:9")
    monkeypatch.setattr(app_module.settings, "backend_timeout_s", 0.5)
    r = _client().get("/search", params={"q": "van"})
    assert r.status_code in (502, 504)
    assert r.json()["error"]["code"] in ("BACKEND_UNREACHABLE", "BACKEND_TIMEOUT")

    class Warming(FakeEngine):
        def search(self, *a):
            return Reply(False, 503, code=ASLEEP, message="MODEL_WARMING")

    monkeypatch.setattr(app_module, "get_provider", lambda s, t=None: Warming())
    r = _client().get("/search", params={"q": "van"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "BACKEND_ASLEEP"


def test_thumb_local_cache_then_engine_fallback(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    _ready_registry()
    client = _client()
    cached = reg.thumbs_dir("aaaaaaaaaaaaaaaa") / "0.jpg"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"\xff\xd8local")
    for key in ("k1", "k2"):  # both footages share the content's thumbs
        r = client.get(f"/thumb/{key}/0.jpg")
        assert r.status_code == 200 and r.content == b"\xff\xd8local"
        assert r.headers["cache-control"] == "public, max-age=86400"

    class Engine(FakeEngine):
        def thumb_bytes(self, cid, shot_id):
            return Reply(True, 200, b"\xff\xd8remote")

    monkeypatch.setattr(app_module, "get_provider", lambda s, t=None: Engine())
    assert client.get("/thumb/k3/7.jpg").content == b"\xff\xd8remote"
    assert (reg.thumbs_dir("bbbbbbbbbbbbbbbb") / "7.jpg").is_file()
    assert client.get("/thumb/k4/0.jpg").status_code == 404  # no content id yet
    assert client.get("/thumb/nope/0.jpg").status_code == 404

    class Asleep(FakeEngine):
        def thumb_bytes(self, cid, shot_id):
            return Reply(False, 503, code=ASLEEP)

    monkeypatch.setattr(app_module, "get_provider", lambda s, t=None: Asleep())
    assert client.get("/thumb/k3/8.jpg").json()["error"]["code"] == "BACKEND_ASLEEP"


# --- handoff -----------------------------------------------------------------------

def test_ready_content_is_reused_without_upload_or_gpu(tmp_path, monkeypatch):
    src = seed_footage(tmp_path)
    engine = FakeEngine(state="ready")
    job, ticks = run_handle(engine, monkeypatch)
    cid = fingerprint.content_id(src)
    assert engine.chunks == [] and engine.submits == 0 and job.reused
    entry = reg.load_registry()["k1"]
    assert entry["state"] == "ready" and entry["reused"] is True and entry["content_id"] == cid
    assert entry["shot_count"] == 5 and entry["duration_s"] == 9.0
    assert sorted(p.name for p in reg.thumbs_dir(cid).iterdir()) == ["0.jpg", "1.jpg"]
    assert job.stages["upload"]["state"] == "done"


def test_missing_content_uploads_in_chunks_then_indexes(tmp_path, monkeypatch):
    src = seed_footage(tmp_path)
    engine = FakeEngine(state="missing", job_state_seq=["running", "running", "done"])
    job, ticks = run_handle(engine, monkeypatch)
    size = src.stat().st_size
    assert engine.chunks == [(0, 1048576), (1048576, 1048576), (2097152, size - 2097152)]
    uploads = [(d, t) for st, d, t in ticks if st == "upload"]
    assert uploads[0] == (0, size) and uploads[-1] == (size, size)  # real bytes, not a timer
    assert ("shots", 3, 4) in ticks  # engine stages mirrored with their own units
    assert engine.submits == 1 and not job.reused
    entry = reg.load_registry()["k1"]
    assert entry["state"] == "ready" and entry["reused"] is False and entry["shot_count"] == 5


def test_partial_upload_resumes_from_engine_offset(tmp_path, monkeypatch):
    seed_footage(tmp_path)
    engine = FakeEngine(state="partial", received=1048576)
    run_handle(engine, monkeypatch)
    assert engine.chunks[0][0] == 1048576 and len(engine.chunks) == 2


def test_offset_mismatch_resyncs_to_engine(tmp_path, monkeypatch):
    seed_footage(tmp_path)
    engine = FakeEngine(state="missing")
    engine.mismatch_once_at = 0
    engine.received = 0
    run_handle(engine, monkeypatch)
    assert engine.chunks[0][0] == 0 and reg.load_registry()["k1"]["state"] == "ready"


def test_live_engine_job_is_attached_not_duplicated(tmp_path, monkeypatch):
    seed_footage(tmp_path)
    engine = FakeEngine(state="indexing")
    run_handle(engine, monkeypatch)
    assert engine.chunks == [] and engine.submits == 0
    assert reg.load_registry()["k1"]["state"] == "ready"


def test_engine_job_error_marks_entry_and_retry_recovers(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    seed_footage(tmp_path)
    engine = FakeEngine(state="missing", job_state_seq=["running", "error"])
    with pytest.raises(RuntimeError, match="decoder exploded") as caught:
        run_handle(engine, monkeypatch)
    # The engine raised its own exception, so the handoff can only say what kind of
    # failure it was (ADR-0021) — never what the exception said.
    assert caught.value.reason == "ENGINE_FAILED"
    entry = reg.load_registry()["k1"]
    assert entry["state"] == "error" and "decoder exploded" in entry["error"]
    jobs_module.jobs._set("job_k1", state="error")
    client = TestClient(app_module.create_app())
    r = client.post("/jobs/job_k1/retry")
    assert r.status_code == 200 and r.json()["footage_key"] == "k1"
    assert reg.load_registry()["k1"]["state"] == "indexing"
    assert client.post("/footage/k1/retry").json()["job_id"] == r.json()["job_id"]  # live job reused
    assert client.post("/footage/../x/retry").status_code == 404


def test_asleep_engine_waits_in_queued_for_backend(tmp_path, monkeypatch):
    seed_footage(tmp_path)
    engine = FakeEngine(state="ready")
    engine.library_replies = [Reply(False, 503, code=ASLEEP)] * 7  # more than the miss budget
    seed_footage(tmp_path)
    engine = FakeEngine(state="ready")
    engine.library_replies = [Reply(False, 503, code=ASLEEP)] * 7  # more than the miss budget
    states = []
    mgr = jobs_module.jobs
    real_set = mgr._set

    def spy(job_id, **fields):
        if "state" in fields:
            states.append(fields["state"])
        return real_set(job_id, **fields)

    monkeypatch.setattr(mgr, "_set", spy)
    run_handle(engine, monkeypatch)
    assert "queued-for-backend" in states and reg.load_registry()["k1"]["state"] == "ready"


def test_unreachable_engine_fails_after_retries(tmp_path, monkeypatch):
    seed_footage(tmp_path)
    engine = FakeEngine()
    engine.library_replies = [Reply(False, 502, code=UNREACHABLE, message="refused")] * 10
    with pytest.raises(RuntimeError, match="BACKEND_UNREACHABLE") as caught:
        run_handle(engine, monkeypatch)
    # The seam's own code is the reason verbatim: the panel already has copy for
    # these three (backends/base.py is the shared vocabulary), so re-inventing a
    # sidecar code for the same thing would give one failure two names.
    assert caught.value.reason == UNREACHABLE
    assert len(engine.library_replies) == 10 - proxy_module.settings.backend_poll_miss_retries
    assert reg.load_registry()["k1"]["state"] == "error"


def test_missing_source_file_is_an_honest_error(tmp_path, monkeypatch):
    seed_footage(tmp_path).unlink()
    with pytest.raises(RuntimeError, match="not found on disk") as caught:
        run_handle(FakeEngine(), monkeypatch)
    assert caught.value.reason == "SOURCE_MISSING"


def test_every_handoff_failure_carries_a_reason_the_panel_can_name(tmp_path, monkeypatch):
    """Each raise site names its own failure, and the vocabulary is closed.

    The reason is the only thing the panel may print, so a raise site without one
    would fall back to "Tempo stopped on this step" — true, and useless. These four
    paths had no test of their own; they are the ones a new call site is most likely
    to copy.
    """
    def handle_for(job_id):
        """A handle for a job the manager does not hold: these two paths fail
        before any registry or engine work, so they need no real job."""
        mgr = jobs_module.jobs
        with mgr._lock:
            mgr._jobs[job_id] = jobs_module.Job(job_id=job_id, footage_key="k1")
        return jobs_module.JobHandle(mgr, job_id)

    # No engine configured at all.
    monkeypatch.setattr(proxy_module, "get_provider", lambda s: None)
    with pytest.raises(RuntimeError) as unconfigured:
        proxy_module.handle(handle_for("job_x"))
    assert unconfigured.value.reason == "NOT_CONFIGURED"

    # A registry entry that is not there (the project dropped the file mid-job).
    monkeypatch.setattr(proxy_module, "get_provider", lambda s: FakeEngine())
    reg.save_registry({})
    with pytest.raises(RuntimeError) as unknown:
        proxy_module.handle(handle_for("job_y"))
    assert unknown.value.reason == "UNKNOWN_FOOTAGE"

    # The engine refusing an application request is neither a transport failure nor
    # the engine's own crash, and the two must not collapse into one another.
    seed_footage(tmp_path)
    engine = FakeEngine(state="missing")
    engine.library_replies = [Reply(False, 409, code="SOURCE_MISSING", message="upload first")]
    with pytest.raises(RuntimeError) as rejected:
        run_handle(engine, monkeypatch)
    assert rejected.value.reason == "ENGINE_REJECTED"

    produced = {unconfigured.value.reason, unknown.value.reason, rejected.value.reason,
                "ENGINE_FAILED", "SOURCE_MISSING", UNREACHABLE, TIMEOUT, ASLEEP}
    assert produced <= proxy_module.REASONS, (
        f"a raise site invented a reason outside the vocabulary: {sorted(produced - proxy_module.REASONS)}"
    )


def test_a_failed_job_carries_the_reason_to_the_status_route():
    """The reason reaches `GET /jobs/{id}`, which is the panel's only source.

    `jobs._run` is the only place a failed job is finalised, and it reads the reason
    off the exception rather than importing `proxy` (which imports `jobs`). Driven
    through a real manager and a real queue so the plumbing is what is tested, not a
    hand-set field.
    """
    from tempo_service.schemas import JobStatus

    def failing(reason):
        mgr = jobs_module.JobManager()
        err = RuntimeError("engine exploded") if reason is None else proxy_module.HandoffError(
            "engine exploded", reason)
        mgr.register_handler(lambda handle: (_ for _ in ()).throw(err))
        job_id = mgr.enqueue("k9")
        deadline = time.time() + 5
        while time.time() < deadline:
            out = mgr.status(job_id)
            if out and out["state"] == "error":
                return out
            time.sleep(0.01)
        pytest.fail("the job never reached error")

    status = JobStatus(**failing("ENGINE_FAILED"))
    assert status.state == "error" and status.reason == "ENGINE_FAILED"
    assert status.error == "engine exploded", "the raw text stays for the log and the registry"

    # An exception that is not a handoff failure has no reason, and the panel's
    # fallback wording is the honest thing to print for it.
    assert failing(None)["reason"] is None

    # A job that has not failed carries none either.
    assert JobStatus(job_id="job_1", footage_key="k7", state="queued").reason is None


def test_thumb_sync_rejects_hostile_names(tmp_path):
    engine = FakeEngine(thumbs={"0.jpg": b"ok", "../evil.jpg": b"x", "sub/1.jpg": b"x", "2.png": b"x"})
    assert proxy_module.sync_thumbs(engine, "dddddddddddddddd") == 1
    assert [p.name for p in reg.thumbs_dir("dddddddddddddddd").iterdir()] == ["0.jpg"]
    assert not (tmp_path / "thumbs" / "evil.jpg").exists()


def test_content_id_matches_engine_copy(tmp_path):
    spec = importlib.util.spec_from_file_location("engine_fingerprint", ENGINE_FP)
    engine_fp = importlib.util.module_from_spec(spec)
    sys.modules["engine_fingerprint"] = engine_fp
    spec.loader.exec_module(engine_fp)
    assert (fingerprint.CHUNK_BYTES, fingerprint.ID_LENGTH) == (engine_fp.CHUNK_BYTES, engine_fp.ID_LENGTH)
    for size in (3, fingerprint.CHUNK_BYTES, fingerprint.CHUNK_BYTES * 2 + 17):
        f = tmp_path / f"f{size}.bin"
        f.write_bytes(bytes(i % 251 for i in range(size)))
        assert fingerprint.content_id(f) == engine_fp.content_id(f)
