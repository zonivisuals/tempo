"""Stage 9 `build_index`: persist matrices + BM25 + metadata (AGENTS.md §3.6).

Writes per footage `<artifact_root>/footage/<key>/`:
- `embeddings.npz` — visual / dialogue / caption matrices (float32, L2-normed)
- `bm25.pkl` — BM25Okapi over `transcript + caption + ocr_text + entities`
  (lowercased, whitespace-split; the research artifact also mixed in
  emotions, which this service does not extract — see `ner.py`)
- `shots.json` — per-shot times, transcript, caption, entities, ocr, cluster
- `meta.json` — fingerprint, format_version, fps, shot count, duration
- `faiss_*.index` — IndexFlatIP per key, scale-up path only (AGENTS.md D3:
  built and stored, never queried without index mapping)
"""

import json
import logging
import pickle
from pathlib import Path

import numpy as np

log = logging.getLogger("tempo.build_index")


def bm25_corpus(shots: list[dict]) -> list[list[str]]:
    docs = []
    for s in shots:
        doc = (
            f"{s.get('transcript', '')} {s.get('caption', '')} "
            f"{s.get('ocr_text', '')} {' '.join(s.get('entities', []))}"
        )
        docs.append(doc.lower().split())
    return docs


def build_index(
    footage_key: str,
    shots: list[dict],
    visual: np.ndarray,
    dialogue: np.ndarray,
    caption: np.ndarray,
    fingerprint: dict,
    fps: float,
    duration_s: float,
    artifact_root: Path,
) -> None:
    from rank_bm25 import BM25Okapi

    root = artifact_root / "footage" / footage_key
    root.mkdir(parents=True, exist_ok=True)

    visual = np.asarray(visual, dtype=np.float32)
    dialogue = np.asarray(dialogue, dtype=np.float32)
    caption = np.asarray(caption, dtype=np.float32)
    np.savez_compressed(
        root / "embeddings.npz", visual=visual, dialogue=dialogue, caption=caption
    )

    with open(root / "bm25.pkl", "wb") as f:
        pickle.dump(BM25Okapi(bm25_corpus(shots)), f)

    serializable = [
        {
            "shot_id": s["shot_id"],
            "start_s": s["start_s"],
            "end_s": s["end_s"],
            "transcript": s.get("transcript", ""),
            "caption": s.get("caption", ""),
            "ocr_text": s.get("ocr_text", ""),
            "entities": s.get("entities", []),
            "cluster_id": s.get("cluster_id", 0),
        }
        for s in shots
    ]
    with open(root / "shots.json", "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)

    with open(root / "meta.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "footage_key": footage_key,
                "fingerprint": fingerprint,
                "format_version": fingerprint.get("format_version"),
                "fps": fps,
                "shot_count": len(shots),
                "duration_s": duration_s,
            },
            f,
            indent=2,
        )

    try:
        import faiss

        for name, mat in (("visual", visual), ("dialogue", dialogue), ("caption", caption)):
            idx = faiss.IndexFlatIP(mat.shape[1])
            idx.add(mat)
            faiss.write_index(idx, str(root / f"faiss_{name}.index"))
    except ImportError:
        log.warning("faiss not installed; skipping stored indexes (D3 scale path)")
    log.info("build_index: %d shots persisted for %s", len(shots), footage_key)
