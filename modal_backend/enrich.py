"""Tier 2: BLIP-2 rep captions + shared NER + multi-key text embeddings.

Mechanical port of `tempo_pipeline_v3.ipynb` cell 4b9c917c — the notebook is the
behavioral reference; this module is the deployable one. Bodies below are
verbatim except the logged deviations. Re-verify against the notebook on any
pipeline change (golden + parity tests guard drift).

Deviations from verbatim:
  - BLIP-2 model name reads env with notebook default;
  - cross-cell names (_get_clip_text_model, _extract_entities) become
    explicit imports; caption hyperparams (40/1.25/3) kept literal;
  - `del x; gc.collect(); …` semicolons kept verbatim (ruff E702 exempt file-wide);
  - _need() guards at entries.
"""
# ruff: noqa: E702
import gc
import re

import numpy as np

from PIL import Image

from . import _deps
from ._deps import _need
from .ner import _extract_entities
from .singletons import _get_clip_text_model

try:
    import torch
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("torch", _err)
    torch = None  # type: ignore[no-redef,assignment]

try:
    from transformers import Blip2ForConditionalGeneration, Blip2Processor
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("transformers", _err)
    Blip2ForConditionalGeneration = None  # type: ignore[no-redef,assignment]
    Blip2Processor = None  # type: ignore[no-redef,assignment]
DEVICE = _deps.device()



def _embed_texts(texts, batch_size=64):
    """Encode strings with the cached CLIP text encoder → L2-normalised (n, 768)."""
    model, proc = _get_clip_text_model()
    all_embs = []
    for start in range(0, len(texts), batch_size):
        batch  = texts[start:start + batch_size]
        inputs = proc(text=batch, return_tensors="pt",
                      padding=True, truncation=True).to(DEVICE)
        with torch.no_grad():
            embs = model(**inputs).text_embeds
        embs = embs / embs.norm(p=2, dim=-1, keepdim=True)
        all_embs.append(embs.cpu().numpy())
    return np.vstack(all_embs).astype(np.float32)


# --- caption fixes -----------------------------------------------------------
# Canonical BLIP-2 prompt, NO transcript/OCR hint. Feeding text_context made
# OPT continue the transcript instead of describing the image. The transcript
# already has its own retrieval key (dialogue) — the caption key must stay
# purely visual or it just duplicates dialogue.
BLIP_PROMPT = "Question: Describe this image. Answer:"


def _clean_caption(raw, max_sentences=3):
    """
    Post-process a raw BLIP-2 decode:
    - drop the 'Question: ... Answer:' scaffold (HF generate returns prompt+output)
    - strip wrapping quotes
    - collapse consecutive repeated sentences (OPT-2.7b degeneration)
    - cap at 3 sentences — CLIP's 77-token encoder was truncating the useful
      part out of long captions anyway
    """
    ans   = raw.split("Answer:")[-1].strip().strip("'\" ")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", ans) if s.strip()]
    dedup = []
    for s in sents:
        if not dedup or s.lower() != dedup[-1].lower():
            dedup.append(s)
    return " ".join(dedup[:max_sentences]).strip()


def _caption_one(blip_proc, blip_model, image):
    inputs = blip_proc(image, text=BLIP_PROMPT,
                       return_tensors="pt").to(DEVICE, torch.float16)
    ids = blip_model.generate(
        **inputs,
        max_new_tokens=40,          # 80 gave repetition loops room to run
        repetition_penalty=1.25,    # breaks self-reinforcing greedy loops
        no_repeat_ngram_size=3,     # hard-bans verbatim trigram repeats
    )
    raw = blip_proc.batch_decode(ids, skip_special_tokens=True)[0]
    return _clean_caption(raw)


def _load_blip_processor():
    """Load the BLIP-2 processor, self-healing a corrupt tokenizer cache.

    Serde-shaped failure (`did not match any variant ...`) means truncated
    bytes on disk (observed live at tokenizer.json line 250373): purge the
    cached copies and raise retryable, so the next attempt re-downloads
    instead of failing forever. Other errors propagate untouched.
    """
    try:
        return Blip2Processor.from_pretrained(_deps.BLIP2_MODEL_NAME)
    except Exception as exc:
        if "did not match any variant" in str(exc):
            gone = _deps.purge_hf_file(_deps.BLIP2_MODEL_NAME, "tokenizer.json")
            raise RuntimeError(
                f"model cache corrupt (purged {len(gone)} tokenizer copies); "
                f"retry the job"
            ) from exc
        raise


def enrich_with_local_models(shots):
    _need(torch, "torch")
    _need(Blip2Processor, "transformers")
    print("Loading BLIP-2 for cluster reps...")
    blip_proc = _load_blip_processor()
    blip_model = Blip2ForConditionalGeneration.from_pretrained(
        _deps.BLIP2_MODEL_NAME, torch_dtype=torch.float16, device_map="auto"
    )
    blip_model.eval()

    reps = [s for s in shots if s.get("is_cluster_rep")]
    print(f"Captioning {len(reps)} cluster reps...")
    rep_pool = {}   # {cluster_id: [(visual_embedding, caption)]}
    for shot in reps:
        try:
            image = Image.open(shot["keyframe_path"]).convert("RGB")
            cap   = _caption_one(blip_proc, blip_model, image)
            rep_pool.setdefault(shot["cluster_id"], []).append(
                (shot["visual_embedding"], cap)
            )
        except Exception as ex:
            print(f"  BLIP-2 failed shot {shot['shot_id']}: {ex}")

    del blip_model, blip_proc; gc.collect(); torch.cuda.empty_cache()

    # Assign captions: each shot gets its cluster's nearest rep caption by L2
    for shot in shots:
        pool = rep_pool.get(shot["cluster_id"], [])
        shot["caption"] = (
            min(pool, key=lambda r: np.linalg.norm(r[0] - shot["visual_embedding"]))[1]
            if pool else ""
        )

    # NER via the shared extractor on shot text (D5: single extractor both sides;
    # junk filter drops 1-char/digit/orphan-## entities that once poisoned anchor).
    # Emotion branch removed for service parity (indexer/ner.py) — field kept empty
    # so BM25/doc shapes stay stable.
    print("Running NER (shared extractor)...")
    for shot in shots:
        ctx = shot.get("text_context", "").strip()
        try:
            shot["entities"] = _extract_entities(ctx) if ctx else []
        except Exception:
            shot["entities"] = []
        shot["emotions"] = []
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass

    # Multi-key text embeddings — cleaned captions now feed the caption key
    print("Embedding dialogue + caption keys...")
    transcripts = [s["transcript"] or "no dialogue" for s in shots]
    captions    = [s["caption"]    or "no caption"  for s in shots]

    t_embs = _embed_texts(transcripts)
    c_embs = _embed_texts(captions)

    for i, shot in enumerate(shots):
        shot["dialogue_embedding"] = t_embs[i]
        shot["caption_embedding"]  = c_embs[i]

    print("Enrichment complete.")