"""Stage 6 `captions`: BLIP-2 on cluster reps only, then L2 propagation.

Locked rules (AGENTS.md §3.2, research artifact):
- canonical prompt `Question: Describe this image. Answer:`, NO
  transcript/OCR hint (hint made OPT continue the transcript).
- `max_new_tokens=40`, `repetition_penalty=1.25`, `no_repeat_ngram_size=3`.
- post-clean: strip scaffold, collapse consecutive duplicate sentences,
  cap at 3 sentences (CLIP's 77-token encoder truncates anyway).
- non-rep shots inherit the nearest rep's caption (L2 on visual embeddings);
  a shot with no rep pool gets "".
"""

import logging
import re

import numpy as np

log = logging.getLogger("tempo.captions")

BLIP_PROMPT = "Question: Describe this image. Answer:"


def clean_caption(raw: str, max_sentences: int = 3) -> str:
    ans = raw.split("Answer:")[-1].strip().strip("'\" ")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", ans) if s.strip()]
    dedup: list[str] = []
    for s in sents:
        if not dedup or s.lower() != dedup[-1].lower():
            dedup.append(s)
    return " ".join(dedup[:max_sentences]).strip()


def caption_reps(shots: list[dict], rep_ids: set[int], progress=None) -> None:  # type: ignore[no-untyped-def]
    """Captions rep shots in place; propagates to the rest by nearest rep."""
    import torch
    from PIL import Image
    from transformers import Blip2ForConditionalGeneration, Blip2Processor

    from .models import load

    def factory():  # type: ignore[no-untyped-def]
        from .config import settings

        proc = Blip2Processor.from_pretrained(settings.blip2_model_name)
        model = Blip2ForConditionalGeneration.from_pretrained(
            settings.blip2_model_name, torch_dtype=torch.float16, device_map="auto"
        ).eval()
        return proc, model

    proc, model = load("blip2", factory)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    reps = [s for s in shots if s["shot_id"] in rep_ids]
    pool: dict[int, list[tuple[np.ndarray, str]]] = {}
    for i, shot in enumerate(reps):
        image = Image.open(shot["keyframe"]).convert("RGB")
        inputs = proc(image, text=BLIP_PROMPT, return_tensors="pt").to(device, dtype)
        ids = model.generate(
            **inputs,
            max_new_tokens=40,
            repetition_penalty=1.25,
            no_repeat_ngram_size=3,
        )
        raw = proc.batch_decode(ids, skip_special_tokens=True)[0]
        cap = clean_caption(raw)
        pool.setdefault(shot.get("cluster_id", 0), []).append(
            (shot["visual_embedding"], cap)
        )
        if progress is not None:
            progress("captions", i + 1, len(reps))
    log.info("captions: %d reps captioned", len(reps))

    for shot in shots:
        candidates = pool.get(shot.get("cluster_id", 0), [])
        shot["caption"] = (
            min(candidates, key=lambda r: np.linalg.norm(r[0] - shot["visual_embedding"]))[1]
            if candidates
            else ""
        )
