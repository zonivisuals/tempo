"""Tier 2 — cluster-based captions (Florence-2 on one representative per cluster).

Port of notebook cell e47706f8 (`_clean_caption`, `florence_captions`,
`build_captions`). k = caption budget (silhouette optimises separation, not
caption fidelity). Rep = medoid of each cluster. Every shot takes the caption
of its nearest rep; that similarity is kept as caption_conf and down-weights
propagated captions at search time.

Deviations from the notebook:
  - progress = reps captioned; generation settings come from config;
  - failures are logged, never printed.
"""

import logging
import re

import numpy as np

from .. import models
from ..cache import StageCache
from ..config import Profile, settings
from . import Progress

log = logging.getLogger("tempo.engine.captions")

MAX_SENTENCES = 3
KMEANS_SEED = 42
KMEANS_INIT = 10


def clean_caption(text: str, max_sentences: int = MAX_SENTENCES) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip().strip("'\" ")
    out: list[str] = []
    for s in (x.strip() for x in re.split(r"(?<=[.!?])\s+", text)):
        if s and s.lower() not in {o.lower() for o in out}:
            out.append(s)
    return " ".join(out[:max_sentences])


def florence_captions(paths: list[str], prof: Profile, progress: Progress) -> list[str]:
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Florence2ForConditionalGeneration

    dtype = models.torch_dtype()
    dev = models.device()
    model = Florence2ForConditionalGeneration.from_pretrained(prof.caption_model, dtype=dtype).to(dev).eval()
    proc = AutoProcessor.from_pretrained(prof.caption_model)
    log.info("model loaded: %s", prof.caption_model)
    task = settings.caption_task
    caps = []
    progress(0, len(paths))
    for i, p in enumerate(paths):
        img = Image.open(p).convert("RGB")
        try:
            with torch.no_grad():
                inp = proc(text=task, images=img, return_tensors="pt").to(dev, dtype)
                ids = model.generate(**inp, max_new_tokens=settings.caption_max_new_tokens,
                                     num_beams=settings.caption_num_beams, do_sample=False)
            raw = proc.batch_decode(ids, skip_special_tokens=False)[0]
            parsed = proc.post_process_generation(raw, task=task, image_size=img.size)
            caps.append(clean_caption(parsed.get(task, "")))
        except Exception as ex:
            log.warning("caption failed for %s: %s", p, ex)
            caps.append("")
        progress(i + 1, len(paths))
    del model, proc
    models.free_memory()
    log.info("model released: %s", prof.caption_model)
    return caps


def pick_reps(V: np.ndarray, budget: int) -> list[int]:
    """Medoid of each KMeans cluster (all shots when n <= budget)."""
    n = len(V)
    k = min(n, budget)
    if k == n:
        return list(range(n))
    from sklearn.cluster import KMeans

    labels = KMeans(n_clusters=k, random_state=KMEANS_SEED, n_init=KMEANS_INIT).fit_predict(V)
    reps = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if len(idx):
            reps.append(int(idx[np.argmax(V[idx] @ models.l2norm(V[idx].mean(0)))]))
    return reps


def propagate(V: np.ndarray, reps: list[int], captions: list[str]) -> dict:
    sims = V @ V[reps].T
    nearest = sims.argmax(1)
    return {"rep_ids": reps, "rep_captions": captions, "nearest_rep": nearest.tolist(),
            "caption": [captions[j] for j in nearest],
            "caption_conf": np.clip(sims.max(1), 0, 1).astype(float).tolist(),
            "cluster_id": nearest.tolist()}


def build_captions(shots: list[dict], V: np.ndarray, cache: StageCache, prof: Profile,
                   progress: Progress) -> dict:
    reps = pick_reps(V, prof.caption_budget)
    log.info("captioning %d representatives for %d shots", len(reps), len(shots))
    captions = florence_captions([cache.abs(shots[r]["keyframe_path"]) for r in reps], prof, progress)
    return propagate(V, reps, captions)
