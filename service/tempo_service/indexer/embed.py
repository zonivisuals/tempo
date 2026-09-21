"""Stages 2 `visual_embed` + 7 `text_embed`: CLIP ViT-L/14 (AGENTS.md §3.2).

`CLIPVisionModelWithProjection` / `CLIPTextModelWithProjection` +
`CLIPProcessor` (research artifact — not `CLIPModel`). Image batches of 32,
text batches of 64. All outputs L2-normalized float32; text inputs use
`truncation=True` (77-token encoder). Empty keys fall back to "no dialogue" /
"no caption" so no key is ever empty.
"""

import logging

import numpy as np

log = logging.getLogger("tempo.embed")

NO_DIALOGUE = "no dialogue"
NO_CAPTION = "no caption"


def _device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def get_clip_vision():  # type: ignore[no-untyped-def]
    from transformers import CLIPProcessor, CLIPVisionModelWithProjection

    from .models import load

    def factory():  # type: ignore[no-untyped-def]
        import torch

        device = _device()
        return (
            CLIPVisionModelWithProjection.from_pretrained(
                _model_name()
            ).to(device).eval(),
            CLIPProcessor.from_pretrained(_model_name()),
            device,
        )

    return load("clip_vision", factory)


def get_clip_text():  # type: ignore[no-untyped-def]
    from transformers import CLIPProcessor, CLIPTextModelWithProjection

    from .models import load

    def factory():  # type: ignore[no-untyped-def]
        import torch

        device = _device()
        return (
            CLIPTextModelWithProjection.from_pretrained(_model_name()).to(device).eval(),
            CLIPProcessor.from_pretrained(_model_name()),
            device,
        )

    return load("clip_text", factory)


def _model_name() -> str:
    from .config import settings  # local import avoids cycles in tests

    return settings.clip_model_name


def embed_images(paths: list[str], batch_size: int = 32, progress=None) -> np.ndarray:  # type: ignore[no-untyped-def]
    """CLIP image embeddings for keyframe paths, L2-normalized (n, 768)."""
    import torch
    from PIL import Image

    model, processor, device = get_clip_vision()
    embs = []
    for start in range(0, len(paths), batch_size):
        chunk = [Image.open(p).convert("RGB") for p in paths[start : start + batch_size]]
        inputs = processor(images=chunk, return_tensors="pt", padding=True).to(device)
        with torch.no_grad():
            out = model(**inputs).image_embeds
        out = out / out.norm(p=2, dim=-1, keepdim=True)
        embs.append(out.cpu().numpy())
        if progress is not None:
            progress("visual_embed", min(start + batch_size, len(paths)), len(paths))
    return np.vstack(embs).astype(np.float32)


def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """CLIP text embeddings, L2-normalized (n, 768)."""
    import torch

    model, processor, device = get_clip_text()
    embs = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        inputs = processor(text=batch, return_tensors="pt", padding=True, truncation=True).to(
            device
        )
        with torch.no_grad():
            out = model(**inputs).text_embeds
        out = out / out.norm(p=2, dim=-1, keepdim=True)
        embs.append(out.cpu().numpy())
    return np.vstack(embs).astype(np.float32)
