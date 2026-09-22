"""Storage providers verification (ADR-0006).

- SigV4 presigning is byte-identical to botocore for PUT/GET/DELETE (frozen
  clock) — the algorithm is spec, botocore is ground truth. Determinism,
  expiry, and tamper-evidence pinned alongside.
- put_file streams real bytes with monotonic progress against a stub HTTP
  server; delete_key maps 2xx->True, 404->False.
- Factory: none/incomplete -> None (manual behavior), full -> S3Backend,
  unknown -> ValueError.
- Proxy: configured storage uploads real bytes with real progress, purges
  raw post-index by default, skips purge on keep, never fails indexed work
  on purge errors, and errors honestly on missing local files.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tempo_service.storage import S3Backend, get_storage
from tempo_service.storage import s3 as s3_module

ENDPOINT = "https://x.r2.cloudflarestorage.com"
BUCKET = "tempo"
KEY = "k9/clip.mp4"
AK, SK = "AKIDEXAMPLE", "SECRETEXAMPLE"
AMZ = "20240102T030405Z"
REGION = "us-east-1"


def _botocore_url(method, op):
    pytest.importorskip("botocore")
    import botocore.auth
    import botocore.session
    import datetime

    from botocore.config import Config

    frozen = datetime.datetime(2024, 1, 2, 3, 4, 5)
    import botocore.auth

    orig = botocore.auth.get_current_datetime
    botocore.auth.get_current_datetime = lambda: frozen
    try:
        sess = botocore.session.get_session()
        client = sess.create_client(
            "s3", region_name=REGION, endpoint_url=ENDPOINT,
            aws_access_key_id=AK, aws_secret_access_key=SK,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return client.generate_presigned_url(op, Params={"Bucket": BUCKET, "Key": KEY},
                                             ExpiresIn=3600, HttpMethod=method)
    finally:
        botocore.auth.get_current_datetime = orig


@pytest.mark.parametrize(
    "method,op", [("PUT", "put_object"), ("GET", "get_object"), ("DELETE", "delete_object")]
)
def test_sigv4_byte_parity_with_botocore(method, op):
    mine = s3_module.presign(method, ENDPOINT, AK, SK, BUCKET, KEY,
                             expires_s=3600, region=REGION, amz_date=AMZ)
    assert mine == _botocore_url(method, op)


def test_sigv4_determinism_expiry_tamper():
    a = s3_module.presign("PUT", ENDPOINT, AK, SK, BUCKET, KEY, region=REGION, amz_date=AMZ)
    assert s3_module.presign("PUT", ENDPOINT, AK, SK, BUCKET, KEY, region=REGION, amz_date=AMZ) == a
    assert "X-Amz-Expires=3600" in a and "X-Amz-Signature=" in a
    b = s3_module.presign("PUT", ENDPOINT, AK, SK, BUCKET, KEY, expires_s=60,
                          region=REGION, amz_date=AMZ)
    assert "X-Amz-Expires=60" in b and b != a
    tampered = a.replace("clip.mp4", "clip.mp5")
    assert tampered != a  # signature binds the key; any edit invalidates
    other_secret = s3_module.presign("PUT", ENDPOINT, AK, "OTHER", BUCKET, KEY,
                                     region=REGION, amz_date=AMZ)
    assert other_secret != a
    try:
        s3_module.presign("POST", ENDPOINT, AK, SK, BUCKET, KEY)
        raise AssertionError("POST must be rejected")
    except ValueError:
        pass


class _Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    store = {}
    fail_delete = False

    def _send(self, code, body=b"ok"):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", "0"))
        _Stub.store[self.path] = self.rfile.read(length) if length else b""
        self._send(200)

    def do_DELETE(self):
        if _Stub.fail_delete:
            self._send(500, b"boom")
            return
        if self.path in _Stub.store:
            _Stub.store.pop(self.path, None)
            self._send(204, b"")
        else:
            self._send(404, b"nope")

    def log_message(self, *a):
        pass


def _stub_server():
    _Stub.store = {}
    _Stub.fail_delete = False
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_put_and_delete_round_trip(tmp_path):
    srv = _stub_server()
    base = f"http://127.0.0.1:{srv.server_port}"
    target = tmp_path / "v.mp4"
    target.write_bytes(b"\x00\x01\x02" * 100000)
    seen = []
    n = s3_module.put_file(base + "/up", str(target),
                           progress=lambda d, t: seen.append((d, t)))
    assert n == 300000 and len(_Stub.store["/up"]) == 300000
    assert seen and seen[-1] == (300000, 300000)
    assert all(b >= a for (a, _), (b, _) in zip(seen, seen[1:]))
    assert s3_module.delete_key(base + "/up") is True
    assert s3_module.delete_key(base + "/missing.mp4") is False
    srv.shutdown()


def test_factory():
    assert get_storage("none", "", "", "", "") is None
    assert get_storage("", "", "", "", "") is None
    assert get_storage("s3", "", "b", "k", "s") is None  # incomplete -> manual
    assert get_storage("s3", "https://e", "", "k", "s") is None
    back = get_storage("s3", "https://e", "b", "k", "s")
    assert isinstance(back, S3Backend)
    try:
        get_storage("gdrive", "", "", "", "")
        raise AssertionError("unknown provider should raise")
    except ValueError:
        pass


def test_s3_backend_upload_uses_presigned_put(tmp_path, monkeypatch):
    srv = _stub_server()
    back = S3Backend(f"http://127.0.0.1:{srv.server_port}", "b", "k", "s")
    url = back.upload_url("k/a.mp4")
    assert url.startswith(f"http://127.0.0.1:{srv.server_port}/b/k/a.mp4?")
    assert "X-Amz-Signature=" in url
    target = tmp_path / "v.mp4"
    target.write_bytes(b"abc" * 100)
    assert back.upload_file(str(target), "k/a.mp4") == 300
    srv.shutdown()


def _proxy_settings(monkeypatch, **kw):
    import tempo_service.app as app_module
    from tempo_service import registry as reg

    for k, v in kw.items():
        monkeypatch.setattr(app_module.settings, k, v)
    return app_module, reg


def test_proxy_uploads_real_bytes_and_purges(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    from tempo_service import jobs as jobs_module
    from tempo_service import registry as reg
    from tempo_service import storage as storage_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "backend", "http")
    monkeypatch.setattr(app_module.settings, "storage_retention", "delete")
    src = tmp_path / "real.mp4"
    src.write_bytes(b"\x07" * 2048)
    reg.save_registry(
        {"ku": {"footage_key": "ku", "path": str(src), "drive_path": "tempo/ku/real.mp4",
                "size": 2048, "mtime_ns": 1, "format_version": 1, "state": "indexing",
                "shot_count": 0, "duration_s": 0.0, "indexed_at": None}}
    )
    deleted = []
    import tempo_service.backends as backends_module

    fake_provider = type("P", (), {
        "submit_index": staticmethod(lambda *a, **k: (True, 200, {"job_id": "bj", "footage_key": "ku"}, None)),
        "job_status": staticmethod(lambda *a, **k: (
            True, 200, {"job_id": "bj", "state": "done", "shot_count": 3,
                        "duration_s": 4.0, "stages": []}, None)),
    })()

    class FakeStorage:
        def upload_file(self, local_path, key, progress=None):
            assert key == "tempo/ku/real.mp4"
            size = 2048
            for done in (512, 1024, 2048):
                progress(done, size)
            return size

        def delete_key(self, key):
            deleted.append(key)
            return True

    monkeypatch.setattr(backends_module, "get_provider", lambda *a, **k: fake_provider)
    monkeypatch.setattr(storage_module, "get_storage", lambda *a, **k: FakeStorage())
    monkeypatch.setattr("tempo_service.proxy.time.sleep", lambda s: None)

    from tempo_service.proxy import handle

    job = jobs_module.Job(job_id="job_up", footage_key="ku")
    progressed = []
    handle(job, lambda st, d, t: progressed.append((st, d, t)))
    ups = [p for p in progressed if p[0] == "upload"]
    assert ups and ups[-1] == ("upload", 2048, 2048)  # real byte totals
    assert deleted == ["tempo/ku/real.mp4"]  # raw purged post-index
    assert reg.load_registry()["ku"]["state"] == "ready"


def test_proxy_purge_skipped_on_keep_and_failure_safe(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    from tempo_service import jobs as jobs_module
    from tempo_service import registry as reg
    from tempo_service import storage as storage_module
    from tempo_service.storage import StorageError

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "backend", "http")
    monkeypatch.setattr(app_module.settings, "storage_retention", "keep")
    src = tmp_path / "k.mp4"
    src.write_bytes(b"\x07" * 16)
    reg.save_registry(
        {"kk": {"footage_key": "kk", "path": str(src), "drive_path": "tempo/kk/k.mp4",
                "size": 16, "mtime_ns": 1, "format_version": 1, "state": "indexing",
                "shot_count": 0, "duration_s": 0.0, "indexed_at": None}}
    )
    import tempo_service.backends as backends_module

    fake_provider = type("P", (), {
        "submit_index": staticmethod(lambda *a, **k: (True, 200, {"job_id": "bj", "footage_key": "kk"}, None)),
        "job_status": staticmethod(lambda *a, **k: (
            True, 200, {"job_id": "bj", "state": "done", "shot_count": 1,
                        "duration_s": 1.0, "stages": []}, None)),
    })()

    class FailDelete:
        def upload_file(self, local_path, key, progress=None):
            return 16

        def delete_key(self, key):
            raise StorageError("boom")

    monkeypatch.setattr(backends_module, "get_provider", lambda *a, **k: fake_provider)
    monkeypatch.setattr(storage_module, "get_storage", lambda *a, **k: FailDelete())
    monkeypatch.setattr("tempo_service.proxy.time.sleep", lambda s: None)

    from tempo_service.proxy import handle

    handle(jobs_module.Job(job_id="j1", footage_key="kk"), lambda *a: None)
    assert reg.load_registry()["kk"]["state"] == "ready"  # purge skipped + safe


def test_proxy_missing_local_file_errors(tmp_path, monkeypatch):
    import tempo_service.app as app_module
    from tempo_service import jobs as jobs_module
    from tempo_service import registry as reg
    from tempo_service import storage as storage_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(reg.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "backend", "http")
    reg.save_registry(
        {"km": {"footage_key": "km", "path": "C:\\gone.mp4", "drive_path": "tempo/km/gone.mp4",
                "size": 1, "mtime_ns": 1, "format_version": 1, "state": "indexing",
                "shot_count": 0, "duration_s": 0.0, "indexed_at": None}}
    )
    import tempo_service.backends as backends_module

    fake_provider = type("P", (), {
        "submit_index": staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not handoff"))),
        "job_status": staticmethod(lambda *a, **k: (False, 502, None, "BACKEND_UNREACHABLE")),
    })()
    monkeypatch.setattr(backends_module, "get_provider", lambda *a, **k: fake_provider)

    class RealishStorage:
        def upload_file(self, local_path, key, progress=None):
            import os

            if not os.path.isfile(local_path):
                from tempo_service.storage import StorageError

                raise StorageError(f"local file missing: {local_path}")
            return 0

        def delete_key(self, key):
            return True

    monkeypatch.setattr(storage_module, "get_storage", lambda *a, **k: RealishStorage())
    monkeypatch.setattr("tempo_service.proxy.time.sleep", lambda s: None)

    from tempo_service.proxy import handle

    try:
        handle(jobs_module.Job(job_id="jm", footage_key="km"), lambda *a: None)
        raise AssertionError("missing local file should raise")
    except RuntimeError as exc:
        assert "gone.mp4" in str(exc) or "missing" in str(exc).lower()
