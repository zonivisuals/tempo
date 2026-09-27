"""Stage orchestration: build one content's index through the stage cache.

Port of notebook cell b648cd41 (`build_or_load_index`). The stage list is
the single source of truth for stage names: /v1/health serves it, and the
sidecar mirrors it instead of keeping a copy.

Deviations from the notebook:
  - keyed by content id (library entry dir) instead of a video path;
  - `umap` stage dropped (visualization-only); `index` stage added (saves
    the index and renders display thumbs);
  - each stage reports progress and completion through a `Reporter`;
  - `source_cached()` answers whether raw bytes are still needed (only the
    shots and transcribe stages read the video).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import models
from .cache import StageCache
from .config import PIPELINE_VERSION, Profile, config_signature, settings, signature_hash
from .index import SHOT_FIELDS, TempoIndex

log = logging.getLogger("tempo.engine.pipeline")

STAGES = ["shots", "visual", "transcribe", "ocr", "captions", "text", "index"]


@dataclass
class Reporter:
    progress: Callable[[str, int, int], None]
    done: Callable[[str], None]


def _deps(cid: str, prof: Profile) -> dict:
    """Stage dependency dicts (notebook cell b648cd41). Changing one input reruns
    only the stages whose deps contain it."""
    base = {"video": cid, "v": PIPELINE_VERSION}
    d_shot = {**base, "max_shot": settings.max_shot_sec, "frames": list(settings.frame_ratios),
              "frame_side": settings.frame_max_side}
    d_vis = {**d_shot, "model": prof.visual_model}
    d_asr = {**base, "model": prof.whisper_model, "tr": prof.whisper_translate_model,
             "hints": settings.name_hints}
    d_cap = {**d_vis, "model": prof.caption_model, "task": settings.caption_task,
             "budget": prof.caption_budget}
    return {"shots": d_shot, "visual": d_vis, "transcribe": d_asr, "captions": d_cap}


def source_cached(cid: str, lib_dir: Path, prof: Profile) -> bool:
    """True when every stage that reads the video is cached (raw bytes not needed)."""
    d = _deps(cid, prof)
    cache = StageCache(lib_dir)
    return cache.has("shots", d["shots"]) and cache.has("transcribe", d["transcribe"])


def current_signature(prof: Profile) -> str:
    return signature_hash(config_signature(settings, prof))


def build(cid: str, src: Path | None, lib_dir: Path, report: Reporter, prof: Profile | None = None) -> dict:
    """Run every stage (cache-aware) and persist the index. → summary for the job envelope."""
    from .stages import captions, ocr, shots, speech, text, visual

    prof = prof or models.current_profile()
    cache = StageCache(lib_dir)
    d = _deps(cid, prof)
    video = str(src) if src else ""

    def stage(name: str, deps: dict, fn: Callable[[], object]):  # type: ignore[no-untyped-def]
        # Start marker: a failure before the stage's first progress tick (e.g. a model
        # load) is still attributed to this stage.
        report.progress(name, 0, 0)
        out = cache.stage(name, deps, fn)
        report.done(name)
        return out

    def prog(name: str):  # type: ignore[no-untyped-def]
        return lambda done, total: report.progress(name, int(done), int(total))

    def need_video(name: str) -> str:
        if not video:
            raise FileNotFoundError(f"{name} stage needs the source video; upload it again")
        return video

    t0 = time.time()
    shot_data = stage("shots", d["shots"],
                      lambda: shots.detect_shots(need_video("shots"), cache, prog("shots")))
    shot_list = shot_data["shots"]
    V = stage("visual", d["visual"], lambda: visual.build_visual(shot_list, cache, prog("visual")))
    asr = stage("transcribe", d["transcribe"],
                lambda: speech.transcribe(need_video("transcribe"), prof, prog("transcribe")))
    d_ocr = {**d["shots"], "lang": asr["language"], "edge": settings.ocr_edge_min,
             "conf": settings.ocr_min_conf}
    ocr_texts = stage("ocr", d_ocr, lambda: ocr.run_ocr(shot_list, cache, asr["language"], prog("ocr")))
    cap = stage("captions", d["captions"],
                lambda: captions.build_captions(shot_list, V, cache, prof, prog("captions")))
    d_txt = {"asr": d["transcribe"], "ocr": d_ocr, "cap": d["captions"], "ner": settings.ner_model,
             "ner_min": settings.ner_min_score, "emo": settings.emotion_model,
             "emo_min": settings.emotion_min_score, "emb": settings.text_embed_model,
             "pad": settings.dialogue_pad_sec, "minw": settings.min_dialogue_words}
    txt = stage("text", d_txt, lambda: text.build_text_features(shot_list, asr, ocr_texts, cap, prog("text")))

    rep_set = set(cap["rep_ids"])
    merged = [{**{k: s[k] for k in SHOT_FIELDS}, **txt["rows"][i], "ocr_text": ocr_texts[i],
               "caption": cap["caption"][i], "caption_conf": cap["caption_conf"][i],
               "cluster_id": cap["cluster_id"][i], "is_cluster_rep": i in rep_set}
              for i, s in enumerate(shot_list)]
    sig = config_signature(settings, prof)
    meta = {"content_id": cid, "signature": signature_hash(sig), "config": sig,
            "fps": shot_data["fps"], "duration": shot_data["duration"], "language": asr["language"],
            "n_shots": len(shot_list), "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    idx = TempoIndex(lib_dir, meta, merged, txt["vocab"],
                     {"V": V, "D": txt["D"], "D_mask": txt["D_mask"], "C": txt["C"]})
    report.progress("index", 0, 0)
    idx.write_thumbs(prog("index"))
    idx.save()
    report.done("index")
    log.info("index ready: %s, %d shots in %.0fs", cid, len(shot_list), time.time() - t0)
    return {"shot_count": len(shot_list), "duration_s": float(shot_data["duration"]),
            "fps": float(shot_data["fps"])}
