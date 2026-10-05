"""Shared model loaders: lazy, locked singletons reused by indexing and search.

Port of notebook cell 6e0e818c (get_siglip, siglip_image_embeds,
siglip_text_embeds, get_text_embedder, embed_passages, embed_query, get_ner)
plus `free_memory`/`l2norm` from cell 50d52b88. Heavy imports (torch,
transformers, sentence-transformers) happen inside functions so the engine
core imports on CPU CI without the `[ml]` extra.

Deviations from the notebook:
  - one lock per model: search requests (threadpool) and the index worker
    share the query models, and inference on one module is serialized;
  - SigLIP image batches report progress through `on_batch(done)`;
  - `ner_batch` lives here (it needs the model) and delegates cleanup to
    `textproc.clean_entities`;
  - loads are logged (AGENTS.md §7.3). Only the query models (siglip, bge, ner)
    are singletons; Whisper, EasyOCR and Florence-2 load inside their stage
    modules and free themselves with `del` + `free_memory()`, because nothing
    holds a reference this module could look up.
"""

import gc
import logging
import threading
from collections.abc import Callable

import numpy as np

from . import textproc
from .config import profile, settings

log = logging.getLogger("tempo.engine.models")

QUERY_MODELS = ("siglip", "bge", "ner")
# SigLIP 2 was trained on lowercased text padded to 64 tokens; the prompt template
# matches the official zero-shot usage (transformers model_doc/siglip2).
SIGLIP_TEXT_TEMPLATE = "this is a photo of {}."
SIGLIP_MAX_LENGTH = 64

_MODELS: dict = {}
_LOCKS: dict[str, threading.Lock] = {name: threading.Lock() for name in QUERY_MODELS}
_LOAD_LOCK = threading.Lock()
_DEVICE: str | None = None


def l2norm(x) -> np.ndarray:  # type: ignore[no-untyped-def]
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)


def device() -> str:
    """cuda | cpu, resolved once. `auto` probes torch; no torch means cpu."""
    global _DEVICE
    if _DEVICE is None:
        if settings.device in ("cuda", "cpu"):
            _DEVICE = settings.device
        else:
            try:
                import torch

                _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                _DEVICE = "cpu"
        log.info("engine device: %s", _DEVICE)
    return _DEVICE


def gpu() -> bool:
    return device() == "cuda"


def current_profile():  # type: ignore[no-untyped-def]
    return profile(settings, gpu())


def torch_dtype():  # type: ignore[no-untyped-def]
    import torch

    return torch.float16 if gpu() else torch.float32


def free_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _get(name: str, factory: Callable[[], object]):  # type: ignore[no-untyped-def]
    if name not in _MODELS:
        with _LOAD_LOCK:
            if name not in _MODELS:
                _MODELS[name] = factory()
                log.info("model loaded: %s", name)
    return _MODELS[name]


def _as_tensor(out):  # type: ignore[no-untyped-def]
    """get_*_features returns a tensor on older transformers and a model output on newer ones."""
    import torch

    if torch.is_tensor(out):
        return out
    for attr in ("image_embeds", "text_embeds", "pooler_output"):
        v = getattr(out, attr, None)
        if v is not None:
            return v
    return out[0]


def get_siglip():  # type: ignore[no-untyped-def]
    def factory():  # type: ignore[no-untyped-def]
        from transformers import AutoModel, AutoProcessor

        name = current_profile().visual_model
        model = AutoModel.from_pretrained(name, dtype=torch_dtype()).to(device()).eval()
        return model, AutoProcessor.from_pretrained(name)

    return _get("siglip", factory)


def siglip_image_embeds(paths: list[str], on_batch: Callable[[int], None] | None = None) -> np.ndarray:
    import torch
    from PIL import Image

    model, proc = get_siglip()
    out, bs = [], settings.siglip_batch
    for i in range(0, len(paths), bs):
        imgs = [Image.open(p).convert("RGB") for p in paths[i:i + bs]]
        with _LOCKS["siglip"], torch.no_grad():
            pv = proc(images=imgs, return_tensors="pt")["pixel_values"].to(device(), model.dtype)
            out.append(_as_tensor(model.get_image_features(pixel_values=pv)).float().cpu().numpy())
        if on_batch:
            on_batch(min(i + bs, len(paths)))
    return l2norm(np.vstack(out))


def siglip_text_embeds(texts: list[str]) -> np.ndarray:
    import torch

    model, proc = get_siglip()
    texts = [SIGLIP_TEXT_TEMPLATE.format(t.strip().lower()) for t in texts]
    with _LOCKS["siglip"], torch.no_grad():
        inp = proc(text=texts, padding="max_length", max_length=SIGLIP_MAX_LENGTH,
                   truncation=True, return_tensors="pt")
        inp = {k: v.to(device()) for k, v in inp.items()}
        return l2norm(_as_tensor(model.get_text_features(**inp)).float().cpu().numpy())


def get_text_embedder():  # type: ignore[no-untyped-def]
    def factory():  # type: ignore[no-untyped-def]
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(settings.text_embed_model, device=device())

    return _get("bge", factory)


def embed_passages(texts: list[str]) -> np.ndarray:
    model = get_text_embedder()
    with _LOCKS["bge"]:
        return model.encode(list(texts), batch_size=settings.text_embed_batch,
                            normalize_embeddings=True, convert_to_numpy=True,
                            show_progress_bar=False).astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    # bge v1.5: instruction on the short query side only, never on passages.
    return embed_passages([settings.bge_query_prompt + text])[0]


def get_ner():  # type: ignore[no-untyped-def]
    def factory():  # type: ignore[no-untyped-def]
        from transformers import pipeline

        # "first": a word can never be split across two entities (fixes 'A' + '##kita').
        return pipeline("token-classification", model=settings.ner_model,
                        aggregation_strategy="first", device=0 if gpu() else -1)

    return _get("ner", factory)


def ner_batch(texts: list[str]) -> list[list[str]]:
    clipped, idx = textproc.ner_inputs(texts)
    res: list[list[str]] = [[] for _ in clipped]
    if not idx:
        return res
    pipe = get_ner()
    with _LOCKS["ner"]:
        outs = pipe([clipped[i] for i in idx], batch_size=settings.ner_batch)
    if len(idx) == 1 and outs and isinstance(outs[0], dict):
        outs = [outs]
    for i, raw in zip(idx, outs):
        res[i] = textproc.clean_entities(raw, clipped[i], settings.ner_min_score)
    return res


def preload_query_models() -> None:
    """Warm SigLIP (text side), bge and NER so the first search is not cold."""
    siglip_text_embeds(["warm up"])
    embed_query("warm up")
    ner_batch(["Warm up in Tokyo."])
