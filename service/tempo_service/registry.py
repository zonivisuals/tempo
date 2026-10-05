"""Footage registry + fingerprinting + diff (AGENTS.md §3.3).

Fingerprint = (resolved_path, size_bytes, mtime_ns) — cheap, no GB hashing.
Path resolution/normalization happens on the AE side via `File.fsName`;
the service hashes the path string as received.

`footage_key` = first 10 hex chars of sha1(path). The registry is one JSON
file (`<artifact_root>/registry.json`). Each entry also records the footage's
`content_id` once its job derives it (ADR-0008, D16): the engine library and
the local thumb cache are keyed by content, so the same bytes under another
path never index twice (AGENTS.md §3.3, §3.6). Disk is the only durable
state: the service must be restartable at any moment and resume purely from
disk.
"""

import hashlib
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .schemas import FootageItem
from .vocabulary import FOOTAGE_INDEXING, FOOTAGE_STALE

log = logging.getLogger("tempo.registry")

REGISTRY_NAME = "registry.json"
THUMBS_DIR = "thumbs"

# Guards every write. The job worker thread and /sync both mutate this file, and only
# the single-worker queue kept them apart by accident; `update` and `transaction` are
# the only write paths, so the lock cannot be skipped. Reads need no lock: a tmp file
# plus `replace` is atomic, so a reader sees the old file or the new one.
_lock = threading.Lock()


def footage_key_for(path: str) -> str:
    """Deterministic short hash of the fingerprint's path component."""
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]


def registry_path(artifact_root: Path | None = None) -> Path:
    return (artifact_root or settings.artifact_root) / REGISTRY_NAME


def thumbs_dir(content_id: str, artifact_root: Path | None = None) -> Path:
    """Local display-thumb cache, keyed by content (shared by every footage with those bytes)."""
    return (artifact_root or settings.artifact_root) / THUMBS_DIR / content_id


def load_registry(artifact_root: Path | None = None) -> dict:
    """Read registry from disk; missing/corrupt file → empty registry."""
    path = registry_path(artifact_root)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("unreadable registry %s (%s); starting empty", path, exc)
        return {}


def save_registry(registry: dict, artifact_root: Path | None = None) -> None:
    """Write via tmp file + `replace`, so a reader never sees a partial file.

    Takes no lock: `update` and `transaction` are the write interface.
    """
    root = artifact_root or settings.artifact_root
    root.mkdir(parents=True, exist_ok=True)
    path = root / REGISTRY_NAME
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
    tmp.replace(path)


def update(key: str, artifact_root: Path | None = None, clear: tuple[str, ...] = (), **fields) -> bool:
    """Merge `fields` into one entry and drop `clear` from it, under the lock.

    The write path for a single entry. False if the key is unknown.
    """
    with _lock:
        registry = load_registry(artifact_root)
        entry = registry.get(key)
        if entry is None:
            return False
        entry.update(fields)
        for name in clear:
            entry.pop(name, None)
        save_registry(registry, artifact_root)
        return True


def read(key: str, artifact_root: Path | None = None) -> dict | None:
    """One entry, or None. No lock needed; see `_lock`."""
    return load_registry(artifact_root).get(key)


@contextmanager
def transaction(artifact_root: Path | None = None) -> Iterator[dict]:
    """Yield the registry for mutation, holding the lock until close.

    For a change spanning entries, which is `/sync`'s diff + apply. A body that
    raises leaves the file as it was.
    """
    with _lock:
        registry = load_registry(artifact_root)
        yield registry
        save_registry(registry, artifact_root)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _readable(item: FootageItem) -> bool:
    """A stat the host could actually measure. Non-positive size/mtime means
    the file wasn't readable (OneDrive placeholder, media still resolving at
    AE reopen, missing file) — never a real edit, never grounds for a job."""
    return item.size > 0 and item.mtime_ns > 0


def diff(
    footages: list[FootageItem],
    registry: dict,
    format_version: int | None = None,
) -> dict[str, list[str]]:
    """Diff project footage against the registry. The five buckets:

    - added:     unknown key, or a stale entry whose fingerprint matches again
                 (re-import revives it; D7 stale is about absent footage). Only
                 on readable stats.
    - changed:   drift confirmed over consecutive syncs, or a format_version
                 mismatch, which is config-driven and so never debounced.
    - removed:   in the registry, not already stale, absent from the project.
    - unchanged: fingerprint and format_version match, in any non-stale state.
                 `error` stays unchanged so nothing auto-loops on a failure.
    - pending:   unreadable stats, or drift not yet confirmed. Never enqueued;
                 `apply_sync` persists the confirmation counters.
    """
    fmt = settings.format_version if format_version is None else format_version
    need = settings.sync_change_confirmations
    seen: set[str] = set()
    added: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []
    pending: list[str] = []

    for item in footages:
        key = footage_key_for(item.path)
        seen.add(key)
        entry = registry.get(key)
        if entry is None:
            (added if _readable(item) else pending).append(key)
            continue
        if entry.get("state") == FOOTAGE_STALE:
            # Fingerprint matches but the entry was left for dead while the
            # footage was out of the project → revive as added (fresh
            # fingerprint written + job enqueued by apply_sync).
            (added if _readable(item) else pending).append(key)
            continue
        if not _readable(item):
            unchanged.append(key)
            continue
        if (
            entry.get("size") == item.size
            and entry.get("mtime_ns") == item.mtime_ns
            and entry.get("format_version") == fmt
        ):
            unchanged.append(key)
            continue
        if entry.get("format_version") != fmt:
            changed.append(key)
            continue
        pend = entry.get("pending_fp") or {}
        if (pend.get("size"), pend.get("mtime_ns")) == (item.size, item.mtime_ns):
            if int(entry.get("pending_hits", 0)) + 1 >= need:
                changed.append(key)
            else:
                pending.append(key)
        else:
            pending.append(key)

    removed = [
        key
        for key, entry in registry.items()
        if key not in seen and entry.get("state") != FOOTAGE_STALE
    ]
    return {
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
        "pending": pending,
    }


def apply_sync(
    footages: list[FootageItem],
    result: dict[str, list[str]],
    registry: dict,
    format_version: int | None = None,
) -> dict:
    """Update the registry in place for a sync result.

    added/changed entries are (re)created with fresh fingerprints and
    `indexing` state (the handoff job derives `content_id` and flips them to
    `ready`); removed entries are marked `stale`, never deleted (AGENTS.md
    D7 — pruning is explicit).
    """
    fmt = settings.format_version if format_version is None else format_version

    for key in result["added"] + result["changed"]:
        matches = [item for item in footages if footage_key_for(item.path) == key]
        if not matches:
            continue
        item = matches[0]
        registry[key] = {
            "footage_key": key,
            "path": item.path,
            "content_id": "",
            "size": item.size,
            "mtime_ns": item.mtime_ns,
            "item_id": item.item_id,
            "frame_rate": item.frame_rate,
            "format_version": fmt,
            "state": FOOTAGE_INDEXING,
            "shot_count": 0,
            "duration_s": 0.0,
            "indexed_at": None,
            "reused": False,
        }
    for key in result.get("pending", []):
        # Persist debounce counters for known entries only. Unknown keys with
        # unreadable stats need no memory: every sighting holds independently
        # until a readable stat promotes them to added.
        entry = registry.get(key)
        if entry is None:
            continue
        matches = [item for item in footages if footage_key_for(item.path) == key]
        if not matches:
            continue
        item = matches[0]
        cur = entry.get("pending_fp") or {}
        if (cur.get("size"), cur.get("mtime_ns")) == (item.size, item.mtime_ns):
            entry["pending_hits"] = int(entry.get("pending_hits", 0)) + 1
        else:
            entry["pending_fp"] = {"size": item.size, "mtime_ns": item.mtime_ns}
            entry["pending_hits"] = 1
    for key in result["removed"]:
        if key in registry:
            registry[key]["state"] = FOOTAGE_STALE
            registry[key].pop("pending_fp", None)
            registry[key].pop("pending_hits", None)
    for key in result["unchanged"]:
        # Fingerprint confirmed against storage: any pending suspicion is moot.
        entry = registry.get(key)
        if entry is not None:
            entry.pop("pending_fp", None)
            entry.pop("pending_hits", None)
    return registry


def prune_stale(registry: dict) -> list[str]:
    """Drop stale entries from the registry. Returns pruned keys.

    Explicit only (panel button or `prune_stale` config) — never called
    automatically by /sync.
    """
    pruned = [key for key, e in registry.items() if e.get("state") == FOOTAGE_STALE]
    for key in pruned:
        del registry[key]
    return pruned
