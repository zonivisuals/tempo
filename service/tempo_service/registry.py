"""Footage registry + fingerprinting + diff (AGENTS.md §3.3).

Fingerprint = (resolved_path, size_bytes, mtime_ns) — cheap, no GB hashing.
Path resolution/normalization happens on the AE side via `File.fsName`;
the service hashes the path string as received.

`footage_key` = first 10 hex chars of sha1(path). The registry is one JSON
file (`<artifact_root>/registry.json`); per-footage artifacts live under
`footage/<key>/` (AGENTS.md §3.6). Disk is the only durable state: the
service must be restartable at any moment and resume purely from disk.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .schemas import FootageItem

log = logging.getLogger("tempo.registry")

REGISTRY_NAME = "registry.json"


def footage_key_for(path: str) -> str:
    """Deterministic short hash of the fingerprint's path component."""
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]


def registry_path(artifact_root: Path | None = None) -> Path:
    return (artifact_root or settings.artifact_root) / REGISTRY_NAME


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
    root = artifact_root or settings.artifact_root
    root.mkdir(parents=True, exist_ok=True)
    path = root / REGISTRY_NAME
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def diff(
    footages: list[FootageItem],
    registry: dict,
    format_version: int | None = None,
) -> dict[str, list[str]]:
    """Diff project footage against the registry.

    - added:   key not in registry
    - changed: size/mtime differ, or stored format_version mismatches
    - removed: in registry (and not already stale) but absent from project
    - unchanged: fingerprint + format_version match
    """
    fmt = settings.format_version if format_version is None else format_version
    seen: set[str] = set()
    added: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []

    for item in footages:
        key = footage_key_for(item.path)
        seen.add(key)
        entry = registry.get(key)
        if entry is None:
            added.append(key)
        elif (
            entry.get("size") != item.size
            or entry.get("mtime_ns") != item.mtime_ns
            or entry.get("format_version") != fmt
        ):
            changed.append(key)
        else:
            unchanged.append(key)

    removed = [
        key
        for key, entry in registry.items()
        if key not in seen and entry.get("state") != "stale"
    ]
    return {"added": added, "changed": changed, "removed": removed, "unchanged": unchanged}


def apply_sync(
    footages: list[FootageItem],
    result: dict[str, list[str]],
    registry: dict,
    format_version: int | None = None,
) -> dict:
    """Update the registry in place for a sync result.

    added/changed entries are (re)created with fresh fingerprints and
    `indexing` state (P3 flips them to `ready`); removed entries are marked
    `stale`, never deleted (AGENTS.md D7 — pruning is explicit).
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
            "size": item.size,
            "mtime_ns": item.mtime_ns,
            "item_id": item.item_id,
            "frame_rate": item.frame_rate,
            "format_version": fmt,
            "state": "indexing",
            "shot_count": 0,
            "duration_s": 0.0,
            "indexed_at": None,
        }
    for key in result["removed"]:
        if key in registry:
            registry[key]["state"] = "stale"
    return registry


def prune_stale(registry: dict) -> list[str]:
    """Drop stale entries from the registry. Returns pruned keys.

    Explicit only (panel button or `prune_stale` config) — never called
    automatically by /sync.
    """
    pruned = [key for key, e in registry.items() if e.get("state") == "stale"]
    for key in pruned:
        del registry[key]
    return pruned
