"""v4 fusion search — pure, no I/O (AGENTS.md §3.5, ADR-0009).

Port of notebook cell 3de29697 (`_zpos`, `_entity_scores`, `search`).
Matrices, statistics and FAISS indexes are passed in (built by corpus.py);
query vectors, entities and tokens are passed in (encoded by the caller).

Candidate path: FAISS top-K per dense key (+ the anchor centroid) plus the
top-K BM25 and entity hits form the candidate set; raw values for candidates are
recomputed from the matrices, and z-scores use the exact corpus moments
(μ = q·m, σ² = qᵀGq/n − μ²) instead of a full scan. With
n <= `k_candidates` every shot is a candidate and the ranking equals the
notebook's exhaustive `search()` (parity-tested).

Deviations from the notebook:
  - scene dedupe is per (content_id, scene_id) — the corpus can hold many videos;
  - ranking is a stable sort over candidate rows (ties keep row order);
  - `raw_cos.dialogue` is None for shots without a dialogue vector.
  - BM25 is all-zero when its max is <= 0. The notebook kept the raw (negative) scores, which
    happens when rank_bm25's idf floor turns negative (terms shared by most shots) and pushed
    every shot below the `final <= 0` cut.
"""

import re
from dataclasses import dataclass

import numpy as np

COMPONENTS = ("visual", "dialogue", "caption", "bm25", "entity", "anchor")
STD_EPS = 1e-6
MIN_ROWS = 2


def l2norm(x) -> np.ndarray:  # type: ignore[no-untyped-def]
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)


def zpos(x, mask=None, cap: float = 3.0) -> np.ndarray:  # type: ignore[no-untyped-def]
    """Per-key z-score over the shots that have that key, clipped to [0, cap] and scaled to [0, 1].
    Makes text-image and text-text cosines comparable, and keys where nothing stands out contribute ~0.
    (Notebook reference — the exhaustive form; the engine uses `KeyStats` for the same moments.)"""
    x = np.asarray(x, np.float32)
    out = np.zeros_like(x)
    m = np.ones(len(x), bool) if mask is None else np.asarray(mask, bool)
    if m.sum() < MIN_ROWS:
        return out
    sd = x[m].std()
    if sd < STD_EPS:
        return out
    out[m] = np.clip((x[m] - x[m].mean()) / sd, 0, cap) / cap
    return out


@dataclass
class KeyStats:
    """Exact first/second moments of one key matrix: mean row and Gram matrix / n (float64)."""

    n: int
    mean: np.ndarray
    gram: np.ndarray

    @classmethod
    def of(cls, M: np.ndarray, mask: np.ndarray | None = None) -> "KeyStats":
        rows = np.asarray(M if mask is None else M[np.asarray(mask, bool)], np.float64)
        n = len(rows)
        if n == 0:
            d = M.shape[1]
            return cls(0, np.zeros(d), np.zeros((d, d)))
        return cls(n, rows.mean(0), rows.T @ rows / n)

    def moments(self, q: np.ndarray) -> tuple[float, float]:
        q = np.asarray(q, np.float64)
        mu = float(q @ self.mean)
        var = float(q @ self.gram @ q) - mu * mu
        return mu, float(np.sqrt(max(var, 0.0)))

    def z(self, x: np.ndarray, q: np.ndarray, cap: float, valid: np.ndarray | None = None) -> np.ndarray:
        out = np.zeros(len(x), np.float32)
        if self.n < MIN_ROWS:
            return out
        mu, sd = self.moments(q)
        if sd < STD_EPS:
            return out
        z = (np.clip((np.asarray(x, np.float64) - mu) / sd, 0, cap) / cap).astype(np.float32)
        return z if valid is None else np.where(valid, z, np.float32(0))


def entity_scores(q_ents: list[str], shot_entities: list[set[str]], shot_texts: list[str]) -> np.ndarray:
    """Fraction of query entities each shot mentions (entity list or word-bounded in dialogue/OCR).
    `shot_texts` are lowercased: a plain substring test gates the word-boundary regex (same result,
    the regex only runs where the entity text actually occurs)."""
    n = len(shot_texts)
    if not q_ents:
        return np.zeros(n, np.float32)
    out = np.zeros(n, np.float32)
    for e in (q.lower() for q in q_ents):
        pat = re.compile(r"\b" + re.escape(e) + r"\b")
        hit = np.fromiter((e in ents for ents in shot_entities), bool, n)
        for i in np.nonzero(~hit & np.fromiter((e in t for t in shot_texts), bool, n))[0]:
            hit[i] = pat.search(shot_texts[i]) is not None
        out += hit
    return out / len(q_ents)


class Bm25Postings:
    """Okapi BM25 over an inverted index, scoring only documents that contain a query token.
    Built from a `rank_bm25.BM25Okapi` (its idf, k1, b, lengths and term frequencies), so the
    scores equal `BM25Okapi.get_scores` exactly (parity-tested) without its per-document loop."""

    def __init__(self, bm25) -> None:  # type: ignore[no-untyped-def]
        self.n = len(bm25.doc_len)
        self.idf = bm25.idf
        doc_len = np.asarray(bm25.doc_len, np.float64)
        self._norm = bm25.k1 * (1 - bm25.b + bm25.b * doc_len / bm25.avgdl)
        self._k1 = bm25.k1
        postings: dict[str, tuple[list[int], list[int]]] = {}
        for i, freqs in enumerate(bm25.doc_freqs):
            for term, tf in freqs.items():
                docs, tfs = postings.setdefault(term, ([], []))
                docs.append(i)
                tfs.append(tf)
        self._postings = {t: (np.array(d, np.int64), np.array(f, np.float64)) for t, (d, f) in postings.items()}

    def get_scores(self, tokens: list[str]) -> np.ndarray:
        score = np.zeros(self.n, np.float64)
        for q in tokens:
            hit = self._postings.get(q)
            idf = self.idf.get(q) or 0
            if hit is None or not idf:
                continue
            docs, tf = hit
            score[docs] += idf * (tf * (self._k1 + 1) / (tf + self._norm[docs]))
        return score


def _top_rows(index, q: np.ndarray, k: int) -> list[int]:  # type: ignore[no-untyped-def]
    """FAISS top-k rows. I[] are shot rows (IndexIDMap ids for masked keys) — never ranks."""
    if index is None or index.ntotal == 0 or k <= 0:
        return []
    _, ids = index.search(np.asarray(q, np.float32)[None, :], min(k, index.ntotal))
    return [int(i) for i in ids[0] if i >= 0]


def _top_scored(scores: np.ndarray, k: int, tiebreak: np.ndarray | None = None) -> np.ndarray:
    """Rows with a positive score, the k best (by score, then tiebreak) when there are more."""
    rows = np.nonzero(scores > 0)[0]
    if len(rows) <= k:
        return rows
    key = scores[rows] if tiebreak is None else scores[rows] + tiebreak[rows] * 1e-3
    return rows[np.argpartition(-key, k - 1)[:k]]


@dataclass
class Hit:
    row: int
    score: float
    contributions: dict[str, float]
    raw_cos: dict[str, float | None]


def rank(corpus, qv: np.ndarray, qt: np.ndarray, q_ents: list[str], q_tokens: list[str],
         weights: dict[str, float], cap: float, k_candidates: int, top_k: int,
         dedupe_scenes: bool = True) -> list[Hit]:
    """Rank corpus shots for one query. `corpus` provides V, D, D_mask, C, caption_conf, scene_keys,
    shot_entities, shot_texts, bm25, faiss_{visual,dialogue,caption}, stats_{visual,dialogue,caption}."""
    n = corpus.n
    if n == 0:
        return []

    if corpus.bm25 is not None and q_tokens:
        bm = np.asarray(corpus.bm25.get_scores(q_tokens), np.float32)
    else:
        bm = np.zeros(n, np.float32)
    bm = bm / bm.max() if bm.max() > 0 else np.zeros(n, np.float32)

    ent = entity_scores(q_ents, corpus.shot_entities, corpus.shot_texts)
    hit = ent > 0
    centroid = l2norm(corpus.V[hit].mean(0)) if 0 < hit.sum() < n else None

    cand = set(_top_rows(corpus.faiss_visual, qv, k_candidates))
    cand.update(_top_rows(corpus.faiss_dialogue, qt, k_candidates))
    cand.update(_top_rows(corpus.faiss_caption, qt, k_candidates))
    if centroid is not None:
        cand.update(_top_rows(corpus.faiss_visual, centroid, k_candidates))
    cand.update(_top_scored(bm, k_candidates).tolist())
    cand.update(_top_scored(ent, k_candidates, tiebreak=bm).tolist())
    rows = np.array(sorted(cand), dtype=np.int64)
    if len(rows) == 0:
        return []

    Vr = corpus.V[rows]
    vis_raw = Vr @ qv
    dia_raw = corpus.D[rows] @ qt
    cap_raw = corpus.C[rows] @ qt
    has_dia = corpus.D_mask[rows]
    comps = {
        "visual": corpus.stats_visual.z(vis_raw, qv, cap),
        "dialogue": corpus.stats_dialogue.z(dia_raw, qt, cap, valid=has_dia),
        "caption": corpus.stats_caption.z(cap_raw, qt, cap) * corpus.caption_conf[rows],
        "bm25": bm[rows],
        "entity": ent[rows],
        "anchor": (corpus.stats_visual.z(Vr @ centroid, centroid, cap)
                   if centroid is not None else np.zeros(len(rows), np.float32)),
    }
    contrib = {k: np.float32(weights[k]) * comps[k] for k in COMPONENTS}
    final = np.sum([contrib[k] for k in COMPONENTS], axis=0)

    hits: list[Hit] = []
    seen: set = set()
    for j in np.argsort(-final, kind="stable"):
        if len(hits) >= top_k or final[j] <= 0:
            break
        r = int(rows[j])
        scene = corpus.scene_keys[r]
        if dedupe_scenes and scene in seen:
            continue
        seen.add(scene)
        hits.append(Hit(
            row=r, score=float(final[j]),
            contributions={k: float(contrib[k][j]) for k in COMPONENTS},
            raw_cos={"visual": float(vis_raw[j]),
                     "dialogue": float(dia_raw[j]) if has_dia[j] else None,
                     "caption": float(cap_raw[j])},
        ))
    return hits
