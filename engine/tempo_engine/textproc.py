"""Text features: tokenizer, entity cleanup, dialogue windows, query entities.

Port of notebook cells da236107 (tokenize, _clean_entities, text_in_window,
bm25_doc) and 3de29697 (_fuzzy_vocab, query_entities). Pure functions only:
the NER model is passed in as a callable, so this module has no torch import
and is golden-testable on CPU.

Deviations from the notebook:
  - `query_entities` takes `ner(texts) -> list[list[str]]` and the vocabulary
    instead of an index object;
  - entity minimum length / score thresholds come from the caller (config).
"""

import re
from collections.abc import Callable, Iterable

from rapidfuzz.distance import OSA

STOPWORDS = set("""a an the and or but of to in on at for with without is are was were be been being it its this
that these those as by from into over under up down out about i you he she we they me him her us them my your his
their our what which who whom when where why how do does did doing have has had not no so than too very can will
just then there here all any some""".split())
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
NER_MAX_CHARS = 1000
FUZZY_MIN_LEN = 4
FUZZY_SHORT_LEN = 6
NGRAM_MAX = 3
UNIGRAM_MIN_LEN = 3

NerFn = Callable[[list[str]], list[list[str]]]


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, punctuation stripped, stopwords removed, CJK runs as character bigrams."""
    out: list[str] = []
    for t in re.findall(r"\w+", (text or "").lower()):
        if _CJK.search(t):
            out += [t[i:i + 2] for i in range(max(1, len(t) - 1))]
        elif t not in STOPWORDS and (len(t) > 1 or t.isdigit()):
            out.append(t)
    return out


def clean_entities(raw: Iterable[dict], text: str, min_score: float) -> list[str]:
    """Merge fragments that touch with no whitespace between them, then rebuild each entity from the
    source span (not the token string) so casing and '##' pieces can never leak through."""
    spans = sorted((r for r in raw if r.get("start") is not None), key=lambda r: r["start"])
    merged: list[dict] = []
    for r in spans:
        if merged and r["start"] <= merged[-1]["end"]:  # touching or overlapping = same word
            merged[-1]["end"] = max(merged[-1]["end"], r["end"])
            merged[-1]["score"] = max(merged[-1]["score"], float(r["score"]))
        else:
            merged.append({"start": r["start"], "end": r["end"], "score": float(r["score"])})
    ents = []
    for m in merged:
        if m["score"] < min_score:
            continue
        w = re.sub(r"\s+", " ", text[m["start"]:m["end"]]).strip()
        w = re.sub(r"^[\W_]+|[\W_]+$", "", w)
        if len(w) >= 2 and any(c.isalpha() for c in w):
            ents.append(w)
    return ents


def ner_inputs(texts: Iterable[str]) -> tuple[list[str], list[int]]:
    """Truncated texts + indices of the non-empty ones (the only ones sent to the model)."""
    clipped = [(t or "")[:NER_MAX_CHARS] for t in texts]
    return clipped, [i for i, t in enumerate(clipped) if t.strip()]


def text_in_window(segments: list[dict], t0: float, t1: float) -> str:
    """Words (or whole segments when no word timing exists) overlapping [t0, t1]."""
    parts = []
    for seg in segments:
        if seg["end"] <= t0 or seg["start"] >= t1:
            continue
        if seg.get("words"):
            ws = [w["word"] for w in seg["words"] if w["end"] > t0 and w["start"] < t1]
            # Whisper keeps the leading space on words of space-separated languages; CJK words have none.
            if any(w["word"][:1].isspace() for w in seg["words"]) or " " not in seg["text"]:
                parts.append("".join(ws))
            else:
                parts.append(" " + " ".join(ws))
        else:
            parts.append(" " + seg["text"])
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def bm25_doc(shot: dict) -> list[str]:
    parts = [shot["dialogue_en"], shot["caption"], shot["ocr_text"], " ".join(shot["entities"]),
             " ".join(shot["emotions"])]
    if shot["dialogue_src"] != shot["dialogue_en"]:
        parts.append(shot["dialogue_src"])
    return tokenize(" ".join(parts))


def fuzzy_vocab(term: str, keys: Iterable[str]) -> str | None:
    """Closest video entity within 1 edit (<= 6 chars) or 2 edits (longer). Transpositions count once."""
    if len(term) < FUZZY_MIN_LEN:
        return None
    max_d = 1 if len(term) <= FUZZY_SHORT_LEN else 2
    best, best_d = None, max_d + 1
    for k in keys:
        if abs(len(k) - len(term)) <= max_d:
            d = OSA.distance(term, k)
            if d < best_d:
                best, best_d = k, d
    return best


def query_entities(query: str, vocab: dict[str, str], ner: NerFn) -> list[str]:
    """Lowercase entity keys for a query: NER as typed (trusted even if unseen), NER on the title-cased
    query (kept only if the video knows it), then 1–3-grams against the vocabulary, typo tolerant."""
    keys = list(vocab)

    def resolve(term: str) -> str | None:
        t = term.lower()
        return t if t in vocab else fuzzy_vocab(t, keys)

    as_typed, titled = ner([query, query.title()])
    found = [resolve(e) or e.lower() for e in as_typed]
    found += [r for r in (resolve(e) for e in titled) if r]
    toks = re.findall(r"\w+", query.lower())
    for n in range(NGRAM_MAX, 0, -1):
        for i in range(len(toks) - n + 1):
            g = " ".join(toks[i:i + n])
            if n == 1 and (g in STOPWORDS or len(g) < UNIGRAM_MIN_LEN):
                continue
            r = resolve(g)
            if r:
                found.append(r)
    return list(dict.fromkeys(found))
