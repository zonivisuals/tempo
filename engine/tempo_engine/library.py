"""Content-addressed library + resumable uploads (ADR-0008, D16).

Layout under `data_root`:
  uploads/<cid>.part + <cid>.json   in-flight upload (bytes + {size, ext})
  raw/<cid>/source<ext>             complete, verified upload (purged after index)
  library/<cid>/                    stage cache, frames, thumbs, index.json/npz

An upload is only accepted at the exact current offset (a retry after a
dropped tunnel resumes instead of duplicating bytes). When the last byte
lands, the content id is re-derived from the file; a mismatch discards the
upload. Everything is keyed by content id, so the same footage under any path,
project or machine maps to the same library entry.
"""

import json
import logging
import os
import re
import shutil
import tarfile
import threading
from pathlib import Path

from . import atomic, fingerprint
from .index import INDEX_JSON, THUMBS_DIR, TempoIndex

log = logging.getLogger("tempo.engine.library")

UPLOADS, RAW, LIBRARY = "uploads", "raw", "library"
RAW_STEM = "source"
DEFAULT_EXT = ".bin"
THUMBS_TAR = "thumbs.tar"
_EXT_RE = re.compile(r"\.[a-z0-9]{1,8}")


class OffsetMismatch(Exception):
    def __init__(self, received: int) -> None:
        super().__init__(f"expected offset {received}")
        self.received = received


class ContentMismatch(Exception):
    pass


def _safe_ext(name: str) -> str:
    ext = Path(name or "").suffix.lower()
    return ext if _EXT_RE.fullmatch(ext) else DEFAULT_EXT


def _atomic_json(path: Path, obj: dict) -> None:
    atomic.write_json(path, obj)


class Library:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        for sub in (UPLOADS, RAW, LIBRARY):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock(self, cid: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(cid, threading.Lock())

    # --- paths -------------------------------------------------------------
    def entry_dir(self, cid: str) -> Path:
        d = self.root / LIBRARY / cid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _part(self, cid: str) -> Path:
        return self.root / UPLOADS / f"{cid}.part"

    def _meta(self, cid: str) -> Path:
        return self.root / UPLOADS / f"{cid}.json"

    def raw(self, cid: str) -> Path | None:
        d = self.root / RAW / cid
        if not d.is_dir():
            return None
        return next((p for p in d.glob(RAW_STEM + ".*") if p.is_file()), None)

    # --- uploads -----------------------------------------------------------
    def upload_state(self, cid: str) -> dict:
        raw = self.raw(cid)
        if raw is not None:
            size = raw.stat().st_size
            return {"content_id": cid, "received": size, "size": size, "complete": True}
        part, meta = self._part(cid), self._meta(cid)
        if part.is_file() and meta.is_file():
            size = int(json.loads(meta.read_text(encoding="utf-8"))["size"])
            return {"content_id": cid, "received": part.stat().st_size, "size": size, "complete": False}
        return {"content_id": cid, "received": 0, "size": 0, "complete": False}

    def append(self, cid: str, offset: int, size: int, name: str, data: bytes) -> dict:
        """Append one chunk at `offset`. Raises OffsetMismatch / ContentMismatch."""
        with self._lock(cid):
            state = self.upload_state(cid)
            if state["complete"]:
                if state["size"] != size:
                    raise ContentMismatch("size differs from the stored upload")
                return state
            if offset != state["received"]:
                raise OffsetMismatch(state["received"])
            part, meta = self._part(cid), self._meta(cid)
            if offset == 0:
                _atomic_json(meta, {"size": size, "ext": _safe_ext(name)})
                part.write_bytes(b"")
            elif state["size"] != size:
                raise ContentMismatch("size differs from the upload in progress")
            if offset + len(data) > size:
                raise ContentMismatch("chunk runs past the declared size")
            with open(part, "ab") as f:
                f.write(data)
            received = offset + len(data)
            if received < size:
                return {"content_id": cid, "received": received, "size": size, "complete": False}
            return self._finish(cid, part, meta)

    def _finish(self, cid: str, part: Path, meta: Path) -> dict:
        got = fingerprint.content_id(part)
        if got != cid:
            part.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            raise ContentMismatch(f"uploaded bytes hash to {got}, not {cid}")
        ext = json.loads(meta.read_text(encoding="utf-8"))["ext"]
        dest = self.root / RAW / cid / (RAW_STEM + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part, dest)
        meta.unlink(missing_ok=True)
        size = dest.stat().st_size
        log.info("upload complete: %s (%d bytes)", cid, size)
        return {"content_id": cid, "received": size, "size": size, "complete": True}

    def purge_raw(self, cid: str) -> None:
        d = self.root / RAW / cid
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            log.info("raw purged: %s", cid)

    # --- indexes -----------------------------------------------------------
    def index_state(self, cid: str, signature: str) -> str | None:
        """ready | stale | None (no index)."""
        d = self.root / LIBRARY / cid
        if not TempoIndex.exists(d):
            return None
        try:
            meta = TempoIndex.read_meta(d)
        except (OSError, ValueError, KeyError):
            return None
        return "ready" if meta.get("signature") == signature else "stale"

    def index_meta(self, cid: str) -> dict:
        return TempoIndex.read_meta(self.root / LIBRARY / cid)

    def ready_ids(self, signature: str) -> list[str]:
        base = self.root / LIBRARY
        return sorted(d.name for d in base.iterdir()
                      if d.is_dir() and fingerprint.valid(d.name) and self.index_state(d.name, signature) == "ready")

    def thumb(self, cid: str, shot_id: int) -> Path:
        return self.root / LIBRARY / cid / THUMBS_DIR / f"{int(shot_id)}.jpg"

    def thumbs_tar(self, cid: str) -> Path:
        """One uncompressed tar of every display thumb, rebuilt when the index is newer."""
        d = self.root / LIBRARY / cid
        tar_path = d / THUMBS_TAR
        with self._lock(cid):
            if not tar_path.is_file() or tar_path.stat().st_mtime_ns < (d / INDEX_JSON).stat().st_mtime_ns:
                tmp = tar_path.with_suffix(".tmp")
                with tarfile.open(tmp, "w") as tar:
                    for p in sorted((d / THUMBS_DIR).glob("*.jpg")):
                        tar.add(p, arcname=p.name)
                os.replace(tmp, tar_path)
        return tar_path
