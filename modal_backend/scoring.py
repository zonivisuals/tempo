"""Pure §3.5 fusion for the Modal backend (ADR-0004).

Same formula as service.search.score_query — same inputs, same outputs —
kept as a separate numpy-only module because the Modal image does not
install the service package. Drift between the two is pinned by the parity
test (service/tests/test_modal_parity.py): identical fixtures must produce
identical finals, winners, and contributions. Changing the formula requires
updating AGENTS.md §3.5, config defaults, and both golden suites together.
"""

import numpy as np

KEY_NAMES = ("visual", "dialogue", "caption")


def score_query(
    q,
    visual,
    dialogue,
    caption,
    bm25_raw,
    query_entities,
    shot_entities,
    text_contexts,
    dense_w=0.45,
    bm25_w=0.40,
    anchor_w=0.15,
    entity_boost=0.15,
):
    """Full fusion for one L2-normalized query vector. Returns per-shot arrays."""
    n = visual.shape[0]
    key_stack = np.vstack([visual @ q, dialogue @ q, caption @ q])
    assert key_stack.shape == (3, n), f"bad key_stack shape {key_stack.shape}"
    best = key_stack.max(axis=0)
    winner = key_stack.argmax(axis=0)
    dense_norm = (best + 1) / 2

    peak = bm25_raw.max() if n else 0.0
    bm25_norm = bm25_raw / peak if peak > 0 else np.zeros(n)

    anchor_norm = np.zeros(n)
    if query_entities:
        qe = [e.lower() for e in query_entities]
        anchored = [
            i for i, ctx in enumerate(text_contexts) if any(e in ctx.lower() for e in qe)
        ]
        if anchored:
            centroid = visual[anchored].mean(axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
                anchor_norm = (visual @ centroid + 1) / 2

    dense_c = dense_w * dense_norm
    bm25_c = bm25_w * bm25_norm
    anchor_c = anchor_w * anchor_norm
    boost = np.zeros(n)
    qe_set = {e.lower() for e in query_entities}
    for i, ents in enumerate(shot_entities):
        if qe_set & {e.lower() for e in ents}:
            boost[i] = entity_boost
    final = dense_c + bm25_c + anchor_c + boost
    return {
        "final": final,
        "winner": winner,
        "key_stack": key_stack,
        "dense_c": dense_c,
        "bm25_c": bm25_c,
        "anchor_c": anchor_c,
        "boost": boost,
    }
