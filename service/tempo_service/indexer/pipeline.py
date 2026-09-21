"""Pipeline orchestration: one footage = one job = 9 stages (AGENTS.md §3.2).

Registered as the single-worker handler (`jobs.register_handler`). Each
stage reports real `{stage, done, total}` progress; models load/unload per
stage (D8) via `indexer.models`. On success the registry entry flips to
`ready` with stats; on failure it flips to `error` and the exception
propagates so the job records the stage + message (F4).
"""

import logging
import os
import traceback
from pathlib import Path

import numpy as np

log = logging.getLogger("tempo.pipeline")


def run_job(job, progress) -> None:  # type: ignore[no-untyped-def]
    from .. import registry as registry_module
    from ..config import settings
    from . import audio, build_index, captions, cluster, embed, ner, ocr, shots
    from . import models as model_slots

    key = job.footage_key
    reg = registry_module.load_registry()
    entry = reg.get(key)
    if entry is None:
        raise RuntimeError(f"footage {key} not in registry")
    path = entry["path"]
    if not os.path.exists(path):
        raise RuntimeError(f"source missing from disk: {path}")

    root = settings.artifact_root / "footage" / key
    thumbs = root / "thumbs"
    fingerprint = {
        "path": entry["path"],
        "size": entry["size"],
        "mtime_ns": entry["mtime_ns"],
        "format_version": settings.format_version,
    }

    try:
        # 1. shots
        shot_list, fps, duration_s = shots.detect_shots(path, str(thumbs), progress)
        # 2. visual_embed (batch 32) — unload CLIP right after
        visual = embed.embed_images(
            [s["keyframe"] for s in shot_list],
            batch_size=settings.visual_embed_batch,
            progress=progress,
        )
        model_slots.unload("clip_vision")
        # 3. cluster
        labels, reps = cluster.cluster_shots(visual)
        for s, lab in zip(shot_list, labels):
            s["cluster_id"] = int(lab)
            s["visual_embedding"] = visual[s["shot_id"]]
        rep_ids = {shot_list[i]["shot_id"] for i in reps}
        # 4. transcribe + word alignment
        segments, _lang = audio.transcribe(path)
        model_slots.unload("whisper")
        audio.assign_text_to_shots(shot_list, segments)
        # 5. OCR (refreshes text_context)
        ocr.extract_ocr(shot_list, progress)
        model_slots.unload("easyocr")
        # 6. captions (reps only + L2 propagation) — unload BLIP-2 after
        captions.caption_reps(shot_list, rep_ids, progress)
        model_slots.unload("blip2")
        # 7. text_embed (dialogue + caption keys)
        dialogue = embed.embed_texts(
            [s.get("transcript") or embed.NO_DIALOGUE for s in shot_list]
        )
        caption = embed.embed_texts(
            [s.get("caption") or embed.NO_CAPTION for s in shot_list]
        )
        model_slots.unload("clip_text")
        # 8. NER (shared extractor)
        ner.extract_shot_entities(shot_list, progress)
        model_slots.unload("ner")
        # 9. build_index + persist
        build_index.build_index(
            key, shot_list, visual, dialogue, caption,
            fingerprint, fps, duration_s, settings.artifact_root,
        )
        progress("build_index", 1, 1)

        entry.update(
            {
                "state": "ready",
                "shot_count": len(shot_list),
                "duration_s": duration_s,
                "indexed_at": registry_module.now_iso(),
                "size": entry["size"],
            }
        )
        # Re-read fingerprint in case the file changed mid-index (cheap guard:
        # if size/mtime drifted, the next /sync will mark it changed anyway).
        reg[key] = entry
        registry_module.save_registry(reg)
        log.info("pipeline done: %s (%d shots)", key, len(shot_list))
    except Exception as exc:
        reg = registry_module.load_registry()
        if key in reg:
            reg[key]["state"] = "error"
            reg[key]["error"] = str(exc)[:500]
            registry_module.save_registry(reg)
        log.error("pipeline failed for %s:\n%s", key, traceback.format_exc())
        raise


def register(manager=None) -> None:  # type: ignore[no-untyped-def]
    from ..jobs import jobs as default_jobs

    (manager or default_jobs).register_handler(run_job)
