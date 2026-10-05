"""Atomic file writes.

Every durable artifact goes through here: tmp file, then `os.replace`, which is
atomic on POSIX and on Windows. A reader sees the old file or the new one and
never a half-written one, so a crash mid-write reads as a miss rather than as
corrupt data.

One helper per package, not one shared. The two packages deploy separately
(`pip install ./service`, `pip install ./engine`), so a shared module would mean
a third package or a vendored copy, which is the duplication AGENTS.md §8 bans.
Each side therefore owns its implementation and its own idempotency test.

Deliberately absent: `fsync`. Nothing here promises durability across a machine
crash, only across a process crash.
"""

import json
import os
from pathlib import Path


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_json(path: Path, obj: object, **dump_kwargs) -> None:
    """`json.dump` kwargs pass through, so callers keep their own indent/sort."""
    write_bytes(path, json.dumps(obj, **dump_kwargs).encode("utf-8"))
