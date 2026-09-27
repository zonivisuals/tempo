"""Content id (ADR-0008, D16).

Port of the notebook's `video_fingerprint` (cell 50d52b88): a fast content
hash of file size + first and last 4 MiB, lengthened to 16 hex chars for a
library shared by many footages. The sidecar computes the same id before any
upload (`service/tempo_service/fingerprint.py`); a cross-check test pins the
two copies together (AGENTS.md §8).
"""

import hashlib
import os
import re

CHUNK_BYTES = 4 * 1024 * 1024
ID_LENGTH = 16
CONTENT_ID_RE = re.compile(rf"[0-9a-f]{{{ID_LENGTH}}}")


def content_id(path: str | os.PathLike) -> str:
    size = os.path.getsize(path)
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(CHUNK_BYTES))
        if size > CHUNK_BYTES:
            f.seek(max(0, size - CHUNK_BYTES))
            h.update(f.read(CHUNK_BYTES))
    return h.hexdigest()[:ID_LENGTH]


def valid(cid: str) -> bool:
    return bool(CONTENT_ID_RE.fullmatch(cid or ""))
