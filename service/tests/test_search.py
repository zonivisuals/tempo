"""P4 verification: golden scoring contract (AGENTS.md §3.5, §9).

Fixed synthetic corpus (seed 7) with hard-coded expected ordering and
contribution values. Any change to the fusion formula, weights, or
normalization MUST update these numbers plus §3.5 and the decisions log
in the same PR — never silently.
"""

import numpy as np
import pytest

from tempo_service.search import score_query

DENSE_W, BM25_W, ANCHOR_W, ENTITY_BOOST = 0.45, 0.40, 0.15, 0.15


def _corpus():
    rng = np.random.RandomState(7)
    n, d = 5, 8

    def normed(m):
        return (m / np.linalg.norm(m, axis=1, keepdims=True)).astype(np.float32)

    visual = normed(rng.rand(n, d))
    dialogue = normed(rng.rand(n, d))
    caption = normed(rng.rand(n, d))
    q = normed(rng.rand(1, d)).astype(np.float32)[0]
    return {
        "q": q,
        "visual": visual,
        "dialogue": dialogue,
        "caption": caption,
        "bm25": np.array([0.0, 1.5, 3.0, 0.5, 2.0]),
        "query_entities": ["Japan"],
        "shot_entities": [[], ["Japan"], [], ["Osaka"], ["japan"]],
        "contexts": [
            "tokyo bay",
            "sea of japan",
            "city night",
            "osaka street",
            "japan alps",
        ],
    }


def _score(c):
    return score_query(
        c["q"], c["visual"], c["dialogue"], c["caption"], c["bm25"],
        c["query_entities"], c["shot_entities"], c["contexts"],
        DENSE_W, BM25_W, ANCHOR_W, ENTITY_BOOST,
    )


def test_golden_ordering_and_final_scores():
    out = _score(_corpus())
    order = list(np.argsort(-out["final"], kind="stable"))
    assert order == [4, 2, 1, 3, 0]
    assert out["final"].tolist() == pytest.approx(
        [0.575170, 0.922178, 0.934203, 0.605727, 0.994487], abs=1e-5
    )


def test_golden_contributions():
    out = _score(_corpus())
    assert [int(v) for v in out["winner"]] == [2, 0, 1, 0, 0]
    assert out["dense_c"].tolist() == pytest.approx(
        [0.435232, 0.425388, 0.405710, 0.398461, 0.431030], abs=1e-5
    )
    assert out["bm25_c"].tolist() == pytest.approx(
        [0.0, 0.2, 0.4, 0.066667, 0.266667], abs=1e-5
    )
    assert out["anchor_c"].tolist() == pytest.approx(
        [0.139938, 0.146791, 0.128493, 0.140599, 0.146791], abs=1e-5
    )
    assert out["boost"].tolist() == [0.0, 0.15, 0.0, 0.0, 0.15]


def test_bm25_all_zero_stays_zero():
    c = _corpus()
    c["bm25"] = np.zeros(5)
    out = _score(c)
    assert (out["bm25_c"] == 0.0).all()  # 0 if max <= 0 — never NaN


def test_no_query_entities_kills_anchor_and_boost():
    c = _corpus()
    c["query_entities"] = []
    out = _score(c)
    assert (out["anchor_c"] == 0.0).all()
    assert (out["boost"] == 0.0).all()


def test_warm_search_under_300ms():
    """F2 acceptance: warm matmul+BM25 scan < 300 ms (excludes thumbnails)."""
    import time

    rng = np.random.RandomState(0)
    n, d = 5000, 768

    def normed(m):
        return (m / np.linalg.norm(m, axis=1, keepdims=True)).astype(np.float32)

    q = normed(rng.rand(1, d)).astype(np.float32)[0]
    mats = (normed(rng.rand(n, d)), normed(rng.rand(n, d)), normed(rng.rand(n, d)))
    args = (q, *mats, rng.rand(n) * 5, [], [[]] * n, [""] * n,
            DENSE_W, BM25_W, ANCHOR_W, ENTITY_BOOST)
    score_query(*args)  # warm up BLAS threads; the budget below is steady-state
    t0 = time.perf_counter()
    out = score_query(*args)
    assert (time.perf_counter() - t0) * 1000 < 300
    assert len(out["final"]) == n
