"""Content id (ADR-0008, D16): size + first and last 4 MiB, sha1, 16 hex chars.

Mirror of `engine/tempo_engine/fingerprint.py` — the engine re-derives it
from the uploaded bytes and rejects a mismatch, and a cross-check test pins
the two copies together (AGENTS.md §8). Computed in the job handler, never
in /sync (it reads up to 8 MiB).
"""

import hashlib
import os

CHUNK_BYTES = 4 * 1024 * 1024
ID_LENGTH = 16


def content_id(path: str | os.PathLike) -> str:
    size = os.path.getsize(path)
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(CHUNK_BYTES))
        if size > CHUNK_BYTES:
            f.seek(max(0, size - CHUNK_BYTES))
            h.update(f.read(CHUNK_BYTES))
    return h.hexdigest()[:ID_LENGTH]
