"""P2 verification: registry diff/apply/prune (AGENTS.md §3.3)."""

from tempo_service import registry
from tempo_service.schemas import FootageItem


def _item(path="C:\\v\\a.mp4", size=100, mtime_ns=1000, item_id=1):
    return FootageItem(path=path, size=size, mtime_ns=mtime_ns, item_id=item_id)


def test_diff_added_changed_removed_unchanged():
    a, b, c = _item("C:\\v\\a.mp4"), _item("C:\\v\\b.mp4"), _item("C:\\v\\c.mp4")
    reg = {}
    r1 = registry.diff([a, b], reg)
    assert sorted(r1["added"]) == sorted(
        [registry.footage_key_for(a.path), registry.footage_key_for(b.path)]
    )
    registry.apply_sync([a, b], r1, reg)

    # unchanged on re-sync
    r2 = registry.diff([a, b], reg)
    assert r2["unchanged"] == r1["added"] and not r2["added"] and not r2["changed"]

    # size change → changed; missing file → removed
    b2 = _item("C:\\v\\b.mp4", size=999)
    r3 = registry.diff([a, b2, c], reg)
    assert r3["changed"] == [registry.footage_key_for(b.path)]
    assert r3["unchanged"] == [registry.footage_key_for(a.path)]
    assert r3["added"] == [registry.footage_key_for(c.path)]

    registry.apply_sync([a, b2, c], r3, reg)
    r4 = registry.diff([a, b2], reg)  # c gone from project
    assert r4["removed"] == [registry.footage_key_for(c.path)]
    registry.apply_sync([a, b2], r4, reg)
    assert reg[registry.footage_key_for(c.path)]["state"] == "stale"


def test_format_bump_forces_reindex_and_prune_is_explicit():
    a = _item()
    reg = {}
    r1 = registry.diff([a], reg, format_version=1)
    registry.apply_sync([a], r1, reg, format_version=1)
    assert registry.diff([a], reg, format_version=2)["changed"] == [
        registry.footage_key_for(a.path)
    ]
    # stale entries survive sync; only prune_stale drops them
    reg[registry.footage_key_for(a.path)]["state"] = "stale"
    assert registry.diff([], reg)["removed"] == []  # already stale → not re-reported
    assert registry.prune_stale(reg) == [registry.footage_key_for(a.path)]
    assert reg == {}
