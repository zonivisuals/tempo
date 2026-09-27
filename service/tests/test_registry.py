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

    # size change → held first (debounce over consecutive syncs), confirmed
    # on repeat; missing file → removed
    b2 = _item("C:\\v\\b.mp4", size=999)
    r3a = registry.diff([a, b2, c], reg)
    assert r3a["pending"] == [registry.footage_key_for(b.path)]
    assert r3a["unchanged"] == [registry.footage_key_for(a.path)]
    assert r3a["added"] == [registry.footage_key_for(c.path)]
    assert not r3a["changed"]
    # stored fingerprint untouched while held (no reset, no re-index grounds)
    assert reg[registry.footage_key_for(b.path)]["size"] == 100
    registry.apply_sync([a, b2, c], r3a, reg)
    r3b = registry.diff([a, b2, c], reg)
    assert r3b["changed"] == [registry.footage_key_for(b.path)]

    registry.apply_sync([a, b2, c], r3b, reg)
    r4 = registry.diff([a, b2], reg)  # c gone from project
    assert r4["removed"] == [registry.footage_key_for(c.path)]
    registry.apply_sync([a, b2], r4, reg)
    assert reg[registry.footage_key_for(c.path)]["state"] == "stale"


def test_stale_revives_on_reimport():
    a = _item()
    key = registry.footage_key_for(a.path)
    reg = {}
    r1 = registry.diff([a], reg)
    registry.apply_sync([a], r1, reg)
    assert reg[key]["state"] == "indexing"
    # footage leaves the project → stale
    r2 = registry.diff([], reg)
    assert r2["removed"] == [key]
    registry.apply_sync([], r2, reg)
    assert reg[key]["state"] == "stale"
    # same file re-imported → added again (revive + re-enqueue), not unchanged
    r3 = registry.diff([a], reg)
    assert r3["added"] == [key] and not r3["unchanged"]
    registry.apply_sync([a], r3, reg)
    assert reg[key]["state"] == "indexing"
    # error entries with matching fingerprint stay put (explicit retry only)
    reg[key]["state"] = "error"
    r4 = registry.diff([a], reg)
    assert r4["unchanged"] == [key] and not r4["added"]


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


def test_unreadable_stats_are_held_not_enqueued():
    """size/mtime <= 0 (OneDrive placeholder, media resolving at AE reopen,
    missing file) is never grounds for a job: unknown keys sit in pending
    until a readable stat promotes them to added."""
    reg = {}
    ghost = _item("C:\\v\\ghost.mp4", size=-1, mtime_ns=0)
    r1 = registry.diff([ghost], reg)
    assert r1["pending"] == [registry.footage_key_for(ghost.path)]
    assert not r1["added"] and not r1["changed"]
    registry.apply_sync([ghost], r1, reg)
    assert registry.footage_key_for(ghost.path) not in reg  # no entry minted
    # readable on the next poll → added immediately (F1 zero-click preserved)
    real = _item("C:\\v\\ghost.mp4", size=50, mtime_ns=500)
    r2 = registry.diff([real], reg)
    assert r2["added"] == [registry.footage_key_for(real.path)]


def test_known_key_unreadable_stays_unchanged():
    """A ready entry reported with bad stats keeps its fingerprint, state,
    and stats — the reopen race that once reset completed footage to
    indexing and queued a duplicate full re-index."""
    a = _item()
    key = registry.footage_key_for(a.path)
    reg = {}
    registry.apply_sync([a], registry.diff([a], reg), reg)
    reg[key]["state"] = "ready"
    reg[key]["shot_count"] = 74
    blind = _item(size=-1, mtime_ns=0)
    r = registry.diff([blind], reg)
    assert r["unchanged"] == [key] and not r["added"] and not r["changed"]
    registry.apply_sync([blind], r, reg)
    assert reg[key]["state"] == "ready"
    assert reg[key]["size"] == 100 and reg[key]["shot_count"] == 74


def test_flapping_stats_reset_the_debounce():
    """A fingerprint that changes again before confirmation restarts the
    counter on the newest values — flapping never confirms."""
    a = _item()
    key = registry.footage_key_for(a.path)
    reg = {}
    registry.apply_sync([a], registry.diff([a], reg), reg)
    v1 = _item(size=101)
    r1 = registry.diff([v1], reg)
    assert r1["pending"] == [key]
    registry.apply_sync([v1], r1, reg)
    assert reg[key]["pending_hits"] == 1
    v2 = _item(size=102)  # different again before confirmation
    r2 = registry.diff([v2], reg)
    assert r2["pending"] == [key] and not r2["changed"]
    registry.apply_sync([v2], r2, reg)
    assert reg[key]["pending_hits"] == 1  # restarted, not accumulated
    assert reg[key]["pending_fp"] == {"size": 102, "mtime_ns": 1000}
    r3 = registry.diff([v2], reg)
    assert r3["changed"] == [key]
