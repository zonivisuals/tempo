"""Index persistence: index.json + index.npz + display thumbs.

Port of notebook cell b648cd41 (`TempoIndex`, `INDEX_ARRAYS`, `SHOT_FIELDS`).

Deviations from the notebook:
  - no UMAP array (visualization-only, AGENTS.md §3.5);
  - BM25 is built by the search corpus, not per index object;
  - `write_thumbs` renders `thumbs/<shot_id>.jpg` at `thumb_width` for the
    sidecar's local cache (bulk-synced as one tar);
  - writes are atomic (tmp + os.replace): a reader never sees half an index.
"""

import json
import os
from pathlib import Path

import numpy as np

from . import atomic
from .config import settings

INDEX_ARRAYS = ("V", "D", "D_mask", "C")
SHOT_FIELDS = ("shot_id", "scene_id", "start_time", "end_time", "duration", "keyframe_path", "frame_paths")
INDEX_JSON = "index.json"
INDEX_NPZ = "index.npz"
THUMBS_DIR = "thumbs"


def _json_default(o):  # type: ignore[no-untyped-def]
    return o.item() if hasattr(o, "item") else str(o)


class TempoIndex:
    def __init__(self, root: Path, meta: dict, shots: list[dict], vocab: dict[str, str],
                 arrays: dict[str, np.ndarray]) -> None:
        self.root, self.meta, self.shots, self.vocab = Path(root), meta, shots, vocab
        self.V = arrays["V"]
        self.D = arrays["D"]
        self.D_mask = arrays["D_mask"].astype(bool)
        self.C = arrays["C"]

    @property
    def content_id(self) -> str:
        return self.meta["content_id"]

    def keyframe(self, i: int) -> str:
        return str(self.root / self.shots[i]["keyframe_path"])

    def thumb(self, shot_id: int) -> Path:
        return self.root / THUMBS_DIR / f"{int(shot_id)}.jpg"

    def save(self) -> None:
        payload = {"meta": self.meta, "shots": self.shots, "vocab": self.vocab}
        # index.json lands last: its presence is what marks the index complete.
        npz_tmp = self.root / (INDEX_NPZ + ".tmp.npz")
        np.savez_compressed(npz_tmp, **{k: getattr(self, k) for k in INDEX_ARRAYS})
        os.replace(npz_tmp, self.root / INDEX_NPZ)
        atomic.write_json(self.root / INDEX_JSON, payload,
                          ensure_ascii=False, default=_json_default)

    def write_thumbs(self, progress) -> None:  # type: ignore[no-untyped-def]
        from PIL import Image

        out = self.root / THUMBS_DIR
        out.mkdir(exist_ok=True)
        n = len(self.shots)
        progress(0, n)
        for i, s in enumerate(self.shots):
            with Image.open(self.keyframe(i)) as img:
                img = img.convert("RGB")
                w, h = img.size
                if w > settings.thumb_width:
                    img = img.resize((settings.thumb_width, max(1, round(h * settings.thumb_width / w))))
                img.save(out / f"{int(s['shot_id'])}.jpg", "JPEG", quality=settings.thumb_quality)
            progress(i + 1, n)

    @staticmethod
    def exists(root: Path) -> bool:
        return (Path(root) / INDEX_JSON).is_file() and (Path(root) / INDEX_NPZ).is_file()

    @staticmethod
    def read_meta(root: Path) -> dict:
        return json.loads((Path(root) / INDEX_JSON).read_text(encoding="utf-8"))["meta"]

    @classmethod
    def load(cls, root: Path) -> "TempoIndex":
        root = Path(root)
        payload = json.loads((root / INDEX_JSON).read_text(encoding="utf-8"))
        with np.load(root / INDEX_NPZ) as z:
            arrays = {k: z[k] for k in INDEX_ARRAYS}
        return cls(root, payload["meta"], payload["shots"], payload["vocab"], arrays)
