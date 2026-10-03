"""Plans and quota enforcement (ADR-0007, amended by ADR-0010).

Free tier locked: 3 footage, 120 footage-minutes. Gates only NEW work —
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


def test_free_allows_three_footage():
    assert entitlements.check_new_work(["a", "b", "c"], [], [], {}, "free")[0] is True


def test_free_denies_fourth_footage():
    ok, code, msg = entitlements.check_new_work(["d"], [], ["a", "b", "c"],
                                                _reg({"a": ("ready", 60.0),
                                                      "b": ("ready", 60.0),
                                                      "c": ("ready", 60.0)}), "free")
    assert (ok, code) == (False, "QUOTA_EXCEEDED")
    assert "3 footage" in msg


def test_unchanged_only_always_passes():
    reg = _reg({"a": ("ready", 8000.0)})  # 133 min, over quota — still viewable
    assert entitlements.check_new_work([], [], ["a"], reg, "free")[0] is True


def test_free_denies_over_duration_on_new_work():
    reg = _reg({"a": ("ready", 7500.0)})  # 125 min already indexed
    ok, code, msg = entitlements.check_new_work([], ["a"], [], reg, "free")
    assert (ok, code) == (False, "QUOTA_EXCEEDED")
    assert "120 footage-minutes" in msg


def test_unknown_plan_fails_closed_to_free():
    ok, _, _ = entitlements.check_new_work(["a", "b", "c", "d"], [], [], {}, "founder-ultra")
    assert ok is False
    assert entitlements.quotas("founder-ultra") == entitlements.quotas("free")


def test_pro_passes_many():
    keys = [f"f{i}" for i in range(10)]
    assert entitlements.check_new_work(keys, [], [], {}, "pro")[0] is True


def test_sync_endpoint_enforces_free_quota(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
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
            {"path": "C:\\v\\c.mp4", "size": 100, "mtime_ns": 1000, "item_id": 3},
        ]})
    assert r2.status_code == 200
    r3 = client.post("/sync", json={
        "footages": [
            {"path": "C:\\v\\a.mp4", "size": 100, "mtime_ns": 1000, "item_id": 1},
            {"path": "C:\\v\\b.mp4", "size": 100, "mtime_ns": 1000, "item_id": 2},
            {"path": "C:\\v\\c.mp4", "size": 100, "mtime_ns": 1000, "item_id": 3},
            {"path": "C:\\v\\d.mp4", "size": 100, "mtime_ns": 1000, "item_id": 4},
        ]})
    assert r3.status_code == 403
    assert r3.json()["error"]["code"] == "QUOTA_EXCEEDED"
    # unchanged re-sync still passes (panel never bricks)
    r4 = client.post("/sync", json=payload("C:\\v\\a.mp4"))
    assert r4.status_code == 200
