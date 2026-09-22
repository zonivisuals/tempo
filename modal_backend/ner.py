"""Shared NER extractor (D5: single extractor query-side and index-side).

Mechanical port of `tempo_pipeline_v3.ipynb` cell cfba7b76 — the notebook is the
behavioral reference; this module is the deployable one. Bodies below are
verbatim except the logged deviations. Re-verify against the notebook on any
pipeline change (golden + parity tests guard drift).

Deviations from verbatim:
  - _get_ner_pipeline becomes an explicit import from .singletons
    (was a notebook global). Body otherwise verbatim.
"""
import re

from .singletons import _get_ner_pipeline



def _merge_split_entities(raw):
    """
    bert-base-NER sometimes labels a '##' continuation token with 'B-'
    (begin), which breaks the pipeline's own aggregation and yields
    fragments like 'A' + '##kita' or 'TO' + '##ST'.
    Re-join any '##' fragment that starts exactly where the previous
    entity ended, regardless of label.
    """
    merged = []
    for e in sorted(raw, key=lambda x: (x.get("start", 0), x.get("end", 0))):
        if (merged
                and e["word"].startswith("##")
                and e.get("start") is not None
                and e["start"] == merged[-1]["end"]):
            prev = merged[-1]
            prev["word"]   += e["word"][2:]           # 'A' + '##kita' → 'Akita'
            prev["end"]     = e.get("end", prev["end"])
            prev["score"]   = max(prev["score"], e["score"])
        else:
            merged.append(dict(e))
    return merged


def _extract_entities(text, score_thr=0.7, max_chars=1000):
    """
    Single source of truth for NER — use for BOTH the query (search_tempo)
    and shot text (enrich_with_local_models) so both sides produce
    comparable entity strings.

    - truncates to max_chars (BERT-NER's limit is 512 TOKENS; the old
      ctx[:512] char-slice was safe but over-conservative)
    - re-joins '##' fragments the aggregator split ('A'+'##kita' → 'Akita')
    - drops junk: orphan '##' bits, 1-char entities, pure digits/symbols
    - strips whitespace, dedupes case-insensitively, keeps first casing
    Returns list[str] — same interface as before.
    """
    if not text or not text.strip():
        return []
    try:
        raw = _get_ner_pipeline()(text[:max_chars])
    except Exception:
        return []

    ents, seen = [], set()
    for e in _merge_split_entities(raw):
        if e.get("score", 0.0) <= score_thr:
            continue
        w = e["word"].strip()
        if w.startswith("##"):                        # orphan fragment, no left neighbour
            continue
        if len(w) < 2 or not any(c.isalpha() for c in w):
            continue
        key = w.lower()
        if key not in seen:
            seen.add(key)
            ents.append(w)
    return ents