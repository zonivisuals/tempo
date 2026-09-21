"""Lazy per-stage model singletons (AGENTS.md D8).

Single consumer GPU (8–12GB) cannot hold CLIP-L + BLIP-2 + Whisper-large-v3
+ EasyOCR + BERT resident. Exactly one heavy model is resident at a time:
each stage loads its model, runs, then unloads. Every transition is logged.
`/health` reports this table so the panel can explain 503s honestly.
"""

import gc
import logging

log = logging.getLogger("tempo.models")

MODELS_LOADED: dict[str, bool] = {
    "clip": False,
    "whisper": False,
    "easyocr": False,
    "blip2": False,
    "ner": False,
}

_singletons: dict[str, object] = {}


def _free() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def load(name: str, factory) -> object:  # type: ignore[no-untyped-def]
    """Load (or reuse) a singleton; evict any other resident heavy model."""
    if name in _singletons:
        return _singletons[name]
    for other in [k for k, v in MODELS_LOADED.items() if v and k != name]:
        unload(other)
    log.info("model load: %s", name)
    obj = factory()
    _singletons[name] = obj
    MODELS_LOADED[name] = True
    return obj


def unload(name: str) -> None:
    if name not in _singletons:
        return
    log.info("model unload: %s", name)
    del _singletons[name]
    MODELS_LOADED[name] = False
    _free()
