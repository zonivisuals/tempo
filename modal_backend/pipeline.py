"""Stage orchestration for one footage (ADR-0004).

Mirrors the notebook main run (cell aca24df8) and the shim's
run_footage_pipeline: Tier 0 → Tier 1 → Tier 2 → index → persist.
Progress reports real units only (counts of shots/segments/reps) — no fake
timers, ever. Artifact layout matches AGENTS.md §3.6 so the service thumb
contract and any offline tooling keep working:

  <out>/shots.json        per-shot times/transcript/caption/entities
  <out>/embeddings.npz    visual / dialogue / caption (float32, L2-normed)
  <out>/bm25.pkl          BM25Okapi over transcript+caption+ocr+entities
  <out>/thumbs/           keyframe_<id>.jpg (written by Tier 0)
"""

import json
import pickle
from pathlib import Path

from . import audio_ocr, enrich, indices, shots_visual

STAGES = [
    "upload",
    "shots",
    "visual_embed",
    "cluster",
    "transcribe",
    "ocr",
    "captions",
    "text_embed",
    "ner",
    "build_index",
]


def run_all(src, out_dir, progress):
    """Run all 9 stages for the footage at src. Returns summary dict.

    src: Path to the footage file (a Volume path on Modal).
    out_dir: Path receiving shots.json / embeddings.npz / bm25.pkl / thumbs/.
    progress: fn(stage, done, total) called with real counts.
    """
    import numpy as np

    src = Path(src)
    out = Path(out_dir)
    thumbs = out / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    if not src.is_file():
        raise FileNotFoundError(f"footage not found: {src}")

    shots = shots_visual.extract_shots_and_keyframes(str(src), out_dir=str(thumbs))
    progress("shots", len(shots), len(shots))

    shots_visual.get_visual_embeddings_and_cluster(shots)
    progress("visual_embed", len(shots), len(shots))
    progress("cluster", len({s.get("cluster_id", 0) for s in shots}), len(shots))

    segments = audio_ocr.transcribe_audio(str(src))
    progress("transcribe", len(segments), max(1, len(segments)))
    audio_ocr.extract_ocr_text(shots)
    progress("ocr", len(shots), len(shots))
    audio_ocr.assign_text_to_shots(shots, segments)

    enrich.enrich_with_local_models(shots)
    progress("captions", sum(1 for s in shots if s.get("caption")), len(shots))
    progress("text_embed", len(shots), len(shots))
    progress("ner", sum(1 for s in shots if "entities" in s), len(shots))

    products = indices.build_search_indices(shots)
    progress("build_index", len(shots), len(shots))

    lite = [
        {
            "shot_id": s["shot_id"],
            "start_s": float(s["start_time"]),
            "end_s": float(s["end_time"]),
            "transcript": s.get("transcript", ""),
            "caption": s.get("caption", ""),
            "ocr_text": s.get("ocr_text", ""),
            "entities": s.get("entities", []),
            "cluster_id": int(s.get("cluster_id", 0)),
        }
        for s in sorted(shots, key=lambda s: s["shot_id"])
    ]
    (out / "shots.json").write_text(json.dumps(lite), encoding="utf-8")
    np.savez_compressed(
        out / "embeddings.npz",
        visual=products["visual"].astype("float32"),
        dialogue=products["dialogue"].astype("float32"),
        caption=products["caption"].astype("float32"),
    )
    with open(out / "bm25.pkl", "wb") as f:
        pickle.dump(products["bm25"], f)

    for s in shots:  # drop frame buffers before anything serializes shots
        s.pop("frame_rgb", None)
        s.pop("frame_bgr", None)
    duration = max((s["end_time"] for s in shots), default=0.0)
    return {"shot_count": len(shots), "duration_s": float(duration)}
