"""Plans and quota enforcement (ADR-0007).

Free tier locked: 1 footage, 7 footage-minutes. Gates only NEW work —
pure unchanged syncs always pass so an over-quota project never bricks
the panel. Unknown plans fail closed to free.
"""

from fastapi.testclient import TestClient

from tempo_service import entitlements, registry


def _reg(entries):
    return {
        k: {"footage_key": k, "path": f"C:\\v\\{k}.mp4", "size": 1,
            "mtime_ns": 1, "format_version": 1, "state": st,
            "shot_count": 0, "duration_s": dur, "indexed_at": None}
        for k, (st, dur) in entries.items()
    }


def test_free_allows_first_footage():
    assert entitlements.check_new_work(["a"], [], [], {}, "free")[0] is True


def test_free_denies_second_footage():
    ok, code, msg = entitlements.check_new_work(["b"], [], ["a"],
                                                _reg({"a": ("ready", 60.0)}), "free")
    assert (ok, code) == (False, "QUOTA_EXCEEDED")
    assert "1 footage" in msg


def test_unchanged_only_always_passes():
    reg = _reg({"a": ("ready", 1200.0)})  # 20 min, over quota — still viewable
    assert entitlements.check_new_work([], [], ["a"], reg, "free")[0] is True


def test_free_denies_over_duration_on_new_work():
    reg = _reg({"a": ("ready", 480.0)})  # 8 min already indexed
    ok, code, msg = entitlements.check_new_work([], ["a"], [], reg, "free")
    assert (ok, code) == (False, "QUOTA_EXCEEDED")
    assert "7 footage-minutes" in msg


def test_unknown_plan_fails_closed_to_free():
    ok, _, _ = entitlements.check_new_work(["a", "b"], [], [], {}, "founder-ultra")
    assert ok is False
    assert entitlements.quotas("founder-ultra") == entitlements.quotas("free")


def test_pro_passes_many():
    keys = [f"f{i}" for i in range(10)]
    assert entitlements.check_new_work(keys, [], [], {}, "pro")[0] is True


def test_sync_endpoint_enforces_free_quota(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "backend", "local")
    monkeypatch.setattr(app_module.settings, "plan", "free")
    client = TestClient(app_module.create_app())

    def payload(path, size=100):
        return {"footages": [{"path": path, "size": size, "mtime_ns": 1000, "item_id": 1}]}

    r1 = client.post("/sync", json=payload("C:\\v\\a.mp4"))
    assert r1.status_code == 200 and len(r1.json()["jobs"]) == 1
    r2 = client.post("/sync", json={
        "footages": [
            {"path": "C:\\v\\a.mp4", "size": 100, "mtime_ns": 1000, "item_id": 1},
            {"path": "C:\\v\\b.mp4", "size": 100, "mtime_ns": 1000, "item_id": 2},
        ]})
    assert r2.status_code == 403
    assert r2.json()["error"]["code"] == "QUOTA_EXCEEDED"
    # unchanged re-sync still passes (panel never bricks)
    r3 = client.post("/sync", json=payload("C:\\v\\a.mp4"))
    assert r3.status_code == 200
