"""Text features — entities, emotions, dialogue windows and text embeddings.

Port of notebook cell da236107 (`build_text_features`). NER runs once per
English segment and once per OCR text, then maps to shots by time; entities
take the most frequent casing in the video (the vocabulary search resolves
against). Shots with fewer than `min_dialogue_words` English words get a zero
dialogue vector and `has_dialogue=False` — never a shared fake one.

Deviations from the notebook:
  - progress = steps (entities, emotions, caption vectors, dialogue vectors);
  - the emotion threshold and window sizes come from config; the emotion
    pipeline is released right after use.
"""

import logging
from collections import Counter

import numpy as np

from .. import models, textproc
from ..config import settings
from . import Progress

log = logging.getLogger("tempo.engine.text")

EMOTION_TOP_K = 3
NO_CAPTION = "no caption"
STEPS = 4


def _emotions(texts: list[str]) -> list[list[str]]:
    from transformers import pipeline

    emo = pipeline("text-classification", model=settings.emotion_model, top_k=EMOTION_TOP_K,
                   device=0 if models.gpu() else -1)
    outs = emo(texts, truncation=True, batch_size=settings.ner_batch)
    del emo
    models.free_memory()
    return [[o["label"] for o in out if o["score"] > settings.emotion_min_score] for out in outs]


def shot_rows(shots: list[dict], asr: dict, ocr_texts: list[str],
              seg_ents: list[list[str]], ocr_ents: list[list[str]]) -> tuple[list[dict], dict]:
    """Per-shot transcript/dialogue windows + canonical entities (pure; tested on CPU)."""
    pad = settings.dialogue_pad_sec
    en_segs = asr["en"]
    vocab: dict[str, str] = {}  # lowercase -> most frequent casing in this video
    for form, _ in Counter(e for lst in seg_ents + ocr_ents for e in lst).most_common():
        vocab.setdefault(form.lower(), form)

    rows = []
    for i, s in enumerate(shots):
        t0, t1 = s["start_time"], s["end_time"]
        w0, w1 = t0 - pad, t1 + pad
        dia_en = textproc.text_in_window(en_segs, w0, w1)
        ents = [e for seg, se in zip(en_segs, seg_ents) if seg["end"] >= w0 and seg["start"] <= w1 for e in se]
        ents += ocr_ents[i]
        rows.append({
            "transcript": textproc.text_in_window(asr["src"], t0, t1),  # exact words inside the shot
            "dialogue_en": dia_en,  # English context window
            "dialogue_src": dia_en if asr["language"] == "en" else textproc.text_in_window(asr["src"], w0, w1),
            "has_dialogue": len(dia_en.split()) >= settings.min_dialogue_words,
            "entities": list(dict.fromkeys(vocab[e.lower()] for e in ents)),
            "emotions": [],
        })
    return rows, vocab


def build_text_features(shots: list[dict], asr: dict, ocr_texts: list[str], cap: dict,
                        progress: Progress) -> dict:
    progress(0, STEPS)
    seg_ents = models.ner_batch([s["text"] for s in asr["en"]])
    ocr_ents = models.ner_batch(ocr_texts)
    rows, vocab = shot_rows(shots, asr, ocr_texts, seg_ents, ocr_ents)
    progress(1, STEPS)

    mask = np.array([r["has_dialogue"] for r in rows], dtype=bool)
    has = np.where(mask)[0]
    if len(has):
        for i, labels in zip(has, _emotions([rows[i]["dialogue_en"] for i in has])):
            rows[i]["emotions"] = labels
    progress(2, STEPS)

    rep_E = models.embed_passages([c or NO_CAPTION for c in cap["rep_captions"]])
    C = rep_E[np.array(cap["nearest_rep"])]
    progress(3, STEPS)
    D = np.zeros((len(shots), rep_E.shape[1]), np.float32)
    if len(has):
        D[has] = models.embed_passages([rows[i]["dialogue_en"] for i in has])
    progress(STEPS, STEPS)
    log.info("text: %d/%d shots with dialogue, %d unique entities", int(mask.sum()), len(shots), len(vocab))
    return {"rows": rows, "D": D, "D_mask": mask, "C": C, "vocab": vocab}
