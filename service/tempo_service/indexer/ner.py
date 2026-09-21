"""Stage 8 `ner`: shared `_extract_entities` extractor (AGENTS.md D5).

Single source of truth for BOTH shot text (index time) and the query
(search time — P4 imports this module). Rules (research artifact):
- `##` subword fragments re-joined at exact token boundaries
  (`A` + `##kita` → `Akita`), regardless of B-/I- label.
- junk dropped: orphan `##` bits, 1-char entities, digit/symbol-only.
- dedupe case-insensitively, keep first casing. Threshold 0.7.

Deliberately NOT ported: the emotion classifier (`j-hartmann/...`) — it has
no retrieval key in the pinned scoring contract (§3.5), so it would only
cost a model load for zero ranking value.
"""

import logging

log = logging.getLogger("tempo.ner")

SCORE_THRESHOLD = 0.7
MAX_CHARS = 1000


def merge_split_entities(raw: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for e in sorted(raw, key=lambda x: (x.get("start", 0), x.get("end", 0))):
        if (
            merged
            and e["word"].startswith("##")
            and e.get("start") is not None
            and e["start"] == merged[-1]["end"]
        ):
            prev = merged[-1]
            prev["word"] += e["word"][2:]
            prev["end"] = e.get("end", prev["end"])
            prev["score"] = max(prev["score"], e["score"])
        else:
            merged.append(dict(e))
    return merged


def _raw_entities(text: str) -> list[dict]:
    from transformers import pipeline

    from .models import load

    def factory():  # type: ignore[no-untyped-def]
        import torch

        from .config import settings

        return pipeline(
            "ner",
            model=settings.ner_model_name,
            aggregation_strategy="simple",
            device=0 if torch.cuda.is_available() else -1,
        )

    ner = load("ner", factory)
    return ner(text[:MAX_CHARS])


def extract_entities(text: str) -> list[str]:
    """Shared extractor — query side and shot side must call this."""
    if not text or not text.strip():
        return []
    try:
        raw = _raw_entities(text)
    except Exception as exc:
        log.warning("ner failed (%s); returning []", exc)
        return []
    entities: list[str] = []
    seen: set[str] = set()
    for e in merge_split_entities(raw):
        if e.get("score", 0.0) <= SCORE_THRESHOLD:
            continue
        word = e["word"].strip()
        if word.startswith("##"):
            continue
        if len(word) < 2 or not any(c.isalpha() for c in word):
            continue
        key = word.lower()
        if key not in seen:
            seen.add(key)
            entities.append(word)
    return entities


def extract_shot_entities(shots: list[dict], progress=None) -> None:  # type: ignore[no-untyped-def]
    for i, shot in enumerate(shots):
        shot["entities"] = extract_entities(shot.get("text_context", "").strip())
        if progress is not None:
            progress("ner", i + 1, len(shots))
