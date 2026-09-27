"""§3.5 v4 fusion: golden ordering + contributions, FAISS-vs-exhaustive parity, exact moments, warm latency."""

import time
from pathlib import Path

import numpy as np
import pytest
from rank_bm25 import BM25Okapi

from tempo_engine import search, textproc
from tempo_engine.corpus import Corpus
from tempo_engine.index import TempoIndex

WEIGHTS = dict(visual=0.35, dialogue=0.25, caption=0.15, bm25=0.15, entity=0.10, anchor=0.05)
CAP = 3.0
WORDS = "tokyo akita road trip dinner neon fog night sleep street vending machine train rain".split()


def make_index(cid: str, seed: int, n: int, dv: int = 16, dt: int = 12) -> TempoIndex:
    rng = np.random.default_rng(seed)
    V = search.l2norm(rng.normal(size=(n, dv)))
    D = search.l2norm(rng.normal(size=(n, dt)))
    mask = rng.random(n) > 0.3
    D[~mask] = 0
    C = search.l2norm(rng.normal(size=(n, dt)))
    shots, vocab = [], {"akita": "Akita", "tokyo": "Tokyo"}
    for i in range(n):
        words = list(rng.choice(WORDS, size=4))
        ents = [vocab[w] for w in words if w in vocab]
        shots.append({"shot_id": i, "scene_id": i // 2, "start_time": float(i), "end_time": float(i + 1),
                      "dialogue_en": " ".join(words) if mask[i] else "", "dialogue_src": "",
                      "caption": f"a {rng.choice(WORDS)} scene", "ocr_text": "", "entities": ents,
                      "emotions": [], "caption_conf": float(rng.uniform(0.5, 1.0)), "transcript": ""})
        shots[-1]["dialogue_src"] = shots[-1]["dialogue_en"]
    return TempoIndex(Path("."), {"content_id": cid}, shots, vocab,
                      {"V": V, "D": D.astype(np.float32), "D_mask": mask, "C": C})


def notebook_search(indexes, qv, qt, q_ents, q_tokens, top_k):
    """Notebook cell 3de29697 `search()`, exhaustive, on the union of the indexes (reference)."""
    shots = [s for ix in indexes for s in ix.shots]
    V = np.vstack([ix.V for ix in indexes])
    D = np.vstack([ix.D for ix in indexes])
    C = np.vstack([ix.C for ix in indexes])
    D_mask = np.concatenate([ix.D_mask for ix in indexes])
    scene = [(ix.content_id, s["scene_id"]) for ix in indexes for s in ix.shots]
    n = len(shots)
    vis_raw, dia_raw, cap_raw = V @ qv, D @ qt, C @ qt
    bm25 = BM25Okapi([textproc.bm25_doc(s) for s in shots])
    bm = np.array(bm25.get_scores(q_tokens), np.float32) if q_tokens else np.zeros(n, np.float32)
    bm = bm / bm.max() if bm.max() > 0 else np.zeros(n, np.float32)  # spec deviation, see search.py
    ent = search.entity_scores(q_ents, [{e.lower() for e in s["entities"]} for s in shots],
                               [f'{s["dialogue_en"]} {s["ocr_text"]}'.lower() for s in shots])
    anchor = np.zeros(n, np.float32)
    hit = ent > 0
    if 0 < hit.sum() < n:
        anchor = search.zpos(V @ search.l2norm(V[hit].mean(0)))
    conf = np.array([s["caption_conf"] for s in shots], np.float32)
    comps = {"visual": search.zpos(vis_raw), "dialogue": search.zpos(dia_raw, D_mask),
             "caption": search.zpos(cap_raw) * conf, "bm25": bm, "entity": ent, "anchor": anchor}
    contrib = {k: WEIGHTS[k] * v for k, v in comps.items()}
    final = np.sum(list(contrib.values()), axis=0)
    out, seen = [], set()
    for i in np.argsort(-final):
        if len(out) >= top_k or final[i] <= 0:
            break
        if scene[i] in seen:
            continue
        seen.add(scene[i])
        out.append((int(i), float(final[i]), {k: float(v[i]) for k, v in contrib.items()}))
    return out


def query(seed: int, corpus: Corpus, entity: str | None):
    rng = np.random.default_rng(seed)
    qv = search.l2norm(rng.normal(size=corpus.V.shape[1]))
    qt = search.l2norm(rng.normal(size=corpus.D.shape[1]))
    q_ents = [entity] if entity else []
    q_tokens = textproc.tokenize(f"road trip {entity or ''}")
    return qv, qt, q_ents, q_tokens


def run(corpus, qv, qt, q_ents, q_tokens, k_candidates, top_k=8):
    return search.rank(corpus, qv, qt, q_ents, q_tokens, WEIGHTS, CAP, k_candidates, top_k)


def test_zpos_matches_notebook_edge_cases():
    assert search.zpos(np.array([0.5])).tolist() == [0.0]  # < 2 rows
    assert search.zpos(np.array([0.3, 0.3, 0.3])).tolist() == [0.0, 0.0, 0.0]  # flat key
    z = search.zpos(np.array([0.0, 1.0, 2.0, 10.0]), mask=[True, True, True, False])
    assert z[3] == 0.0 and z[0] == 0.0 and z[2] == pytest.approx(np.sqrt(1.5) / 3, rel=1e-6)


def test_key_stats_moments_equal_direct_std():
    ix = make_index("a" * 16, 1, 60)
    rng = np.random.default_rng(2)
    for M, mask in ((ix.V, None), (ix.D, ix.D_mask)):
        q = search.l2norm(rng.normal(size=M.shape[1]))
        x = (M @ q)[ix.D_mask] if mask is not None else M @ q
        mu, sd = search.KeyStats.of(M, mask).moments(q)
        assert mu == pytest.approx(float(np.mean(x, dtype=np.float64)), abs=1e-7)
        assert sd == pytest.approx(float(np.std(x, dtype=np.float64)), rel=1e-6)


@pytest.mark.parametrize("entity", [None, "akita"])
def test_candidate_path_equals_notebook_exhaustive(entity):
    indexes = [make_index("a" * 16, 3, 40), make_index("b" * 16, 4, 30)]
    corpus = Corpus(indexes)
    for seed in range(5):
        qv, qt, q_ents, q_tokens = query(seed, corpus, entity)
        ref = notebook_search(indexes, qv, qt, q_ents, q_tokens, top_k=10)
        got = run(corpus, qv, qt, q_ents, q_tokens, k_candidates=corpus.n, top_k=10)
        assert [h.row for h in got] == [r for r, _, _ in ref]
        for h, (_, score, contrib) in zip(got, ref):
            assert h.score == pytest.approx(score, abs=1e-5)
            for k in search.COMPONENTS:
                assert h.contributions[k] == pytest.approx(contrib[k], abs=1e-5)
            assert sum(h.contributions.values()) == pytest.approx(h.score, abs=1e-6)


def test_bm25_postings_equal_rank_bm25():
    docs = [textproc.bm25_doc(s) for s in make_index("a" * 16, 6, 50).shots]
    ref = BM25Okapi(docs)
    fast = search.Bm25Postings(ref)
    for q in (["road", "trip"], ["akita", "akita", "neon"], ["missing"], []):
        assert np.allclose(fast.get_scores(q), ref.get_scores(q), atol=1e-12)


def test_faiss_rows_are_shot_rows_not_ranks():
    corpus = Corpus([make_index("a" * 16, 5, 25)])
    q = corpus.V[17]
    assert search._top_rows(corpus.faiss_visual, q, 1) == [17]
    masked = int(np.nonzero(corpus.D_mask)[0][-1])
    assert search._top_rows(corpus.faiss_dialogue, corpus.D[masked], 1) == [masked]


def test_golden_ordering_and_contributions():
    corpus = Corpus([make_index("a" * 16, 7, 24)])
    qv, qt, q_ents, q_tokens = query(11, corpus, "akita")
    hits = run(corpus, qv, qt, q_ents, q_tokens, k_candidates=512, top_k=5)
    assert [h.row for h in hits] == GOLDEN_ROWS
    assert [round(h.score, 5) for h in hits] == GOLDEN_SCORES
    assert {k: round(v, 5) for k, v in hits[0].contributions.items()} == GOLDEN_TOP_CONTRIB
    assert len({corpus.scene_keys[h.row] for h in hits}) == len(hits)  # one result per scene


def test_bm25_never_negative_when_every_shot_shares_the_terms():
    ix = make_index("a" * 16, 7, 6)
    for s in ix.shots:
        s["dialogue_en"] = s["dialogue_src"] = "akita akita road"
    corpus = Corpus([ix])
    qv, qt, _, _ = query(1, corpus, None)
    hits = run(corpus, qv, qt, [], ["akita", "road"], k_candidates=512)
    assert hits and all(h.contributions["bm25"] == 0.0 for h in hits)


def test_no_entities_kills_entity_and_anchor():
    corpus = Corpus([make_index("a" * 16, 7, 24)])
    qv, qt, _, q_tokens = query(11, corpus, None)
    for h in run(corpus, qv, qt, [], q_tokens, k_candidates=512):
        assert h.contributions["entity"] == 0.0 and h.contributions["anchor"] == 0.0


def test_dialogue_raw_is_none_without_dialogue():
    corpus = Corpus([make_index("a" * 16, 7, 24)])
    qv, qt, q_ents, q_tokens = query(3, corpus, None)
    for h in run(corpus, qv, qt, q_ents, q_tokens, k_candidates=512, top_k=24):
        assert (h.raw_cos["dialogue"] is None) == (not corpus.D_mask[h.row])
        if h.raw_cos["dialogue"] is None:
            assert h.contributions["dialogue"] == 0.0


def test_empty_corpus_returns_nothing():
    assert run(Corpus([]), np.ones(4), np.ones(4), [], [], k_candidates=8) == []


def test_warm_rank_under_300ms_at_10k_shots():
    # CPU contract (AGENTS.md F2). Memory-bandwidth bound: V alone is n x 1152 float32.
    n, rng = 10000, np.random.default_rng(0)
    ix = make_index("c" * 16, 9, 8, dv=1152, dt=768)
    reps = n // len(ix.shots)
    big = TempoIndex(Path("."), {"content_id": "c" * 16},
                     [dict(s, shot_id=i, scene_id=i) for i, s in enumerate(ix.shots * reps)], ix.vocab,
                     {"V": search.l2norm(rng.normal(size=(n, 1152))),
                      "D": search.l2norm(rng.normal(size=(n, 768))),
                      "D_mask": np.ones(n, bool), "C": search.l2norm(rng.normal(size=(n, 768)))})
    corpus = Corpus([big])
    qv, qt, q_ents, q_tokens = query(1, corpus, "akita")
    run(corpus, qv, qt, q_ents, q_tokens, k_candidates=512)
    t0 = time.perf_counter()
    run(corpus, qv, qt, q_ents, q_tokens, k_candidates=512)
    assert time.perf_counter() - t0 < 0.3


# Pinned from the v4 fusion (ADR-0009). Changing weights or fusion math must update these
# together with §3.5 and the decisions log.
GOLDEN_ROWS = [3, 11, 13, 4, 0]
GOLDEN_SCORES = [0.4219, 0.37512, 0.35826, 0.34026, 0.31949]
GOLDEN_TOP_CONTRIB = {"visual": 0.15696, "dialogue": 0.10037, "caption": 0.01457, "bm25": 0.15,
                      "entity": 0.0, "anchor": 0.0}
