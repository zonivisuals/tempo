"""Per-stage cache (ADR-0008 layer 3).

Port of the notebook's `Cache` (cell 50d52b88). Each stage result is pickled
under a hash of its inputs, so a restart or `brev stop` mid-index resumes at
the last finished stage and a config change reruns only the dependent
stages.

Deviations from the notebook:
  - the directory is the library entry `library/<content_id>/` (the engine
    derives the content id; the notebook hashed the video itself);
  - stages live under `stages/`, and writes are atomic (tmp + os.replace) so
    a torn write reads as a miss, never as a corrupt hit;
  - hits and builds are logged instead of printed.
"""

import hashlib
import json
import logging
import pickle
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import atomic

log = logging.getLogger("tempo.engine.cache")

STAGE_DIR = "stages"


def deps_key(deps: dict) -> str:
    return hashlib.sha1(json.dumps(deps, sort_keys=True, default=str).encode()).hexdigest()[:10]


class StageCache:
    def __init__(self, root: Path) -> None:
        self.dir = Path(root)
        (self.dir / STAGE_DIR).mkdir(parents=True, exist_ok=True)

    def abs(self, rel: str) -> str:
        return str(self.dir / rel)

    def path(self, name: str, deps: dict) -> Path:
        return self.dir / STAGE_DIR / f"{name}_{deps_key(deps)}.pkl"

    def has(self, name: str, deps: dict) -> bool:
        return self.path(name, deps).is_file()

    def stage(self, name: str, deps: dict, fn: Callable[[], Any]) -> Any:
        path = self.path(name, deps)
        if path.is_file():
            try:
                with open(path, "rb") as f:
                    out = pickle.load(f)
                log.info("stage %s: cache hit (%s)", name, path.name)
                return out
            except (OSError, pickle.UnpicklingError, EOFError) as exc:
                log.warning("stage %s: unreadable cache %s (%s); rebuilding", name, path, exc)
        t0 = time.time()
        out = fn()
        atomic.write_bytes(path, pickle.dumps(out))
        log.info("stage %s: built in %.1fs", name, time.time() - t0)
        return out
