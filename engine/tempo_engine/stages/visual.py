"""Tier 0 — visual key.

Port of notebook cell f98b5375 (`build_visual`): shot vector = normalised
mean of its 3 frame embeddings (covers motion/actions better than one
frame). Deviation: progress reports frames embedded per SigLIP batch.
"""

import numpy as np

from .. import models
from ..cache import StageCache
from . import Progress


def build_visual(shots: list[dict], cache: StageCache, progress: Progress) -> np.ndarray:
    flat, owner = [], []
    for i, s in enumerate(shots):
        for p in s["frame_paths"]:
            flat.append(cache.abs(p))
            owner.append(i)
    progress(0, len(flat))
    E = models.siglip_image_embeds(flat, on_batch=lambda done: progress(done, len(flat)))
    V = np.zeros((len(shots), E.shape[1]), np.float32)
    np.add.at(V, np.array(owner), E)
    return models.l2norm(V)
