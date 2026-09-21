"""Search scoring exactly per AGENTS.md §3.5 — pure functions, no I/O.

The scoring path takes matrices in and returns results out, which is what
makes golden tests easy (AGENTS.md §7.3). Corpus loading from disk lives in
the clearly-marked I/O section below, never inside `score_query`.

Historical guard (§3.5): dense scores come from direct matmul against the
three key matrices in shots_db row order — every per-shot value is
shot-aligned by construction. Never assign a FAISS `.search()` result
(which returns similarities sorted by rank) positionally to shots.
"""

import logging
import pickle
from pathlib import Path

import numpy as np

log = logging.getLogger("tempo.search")

KEY_NAMES = ("visual", "dialogue", "caption")


def score_query(
    q: np.ndarray,
    visual: np.ndarray,
    dialogue: np.ndarray,
    caption: np.ndarray,
    bm25_raw: np.ndarray,
    query_entities: list[str],
    shot_entities: list[list[str]],
    text_contexts: list[str],
    dense_w: float,
    bm25_w: float,
    anchor_w: float,
    entity_boost: float,
) -> dict:
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
            log.info("anchor centroid from %d shots", len(anchored))

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


# ---------------------------------------------------------------------------
# I/O helpers (disk → matrices). Kept out of the scoring path.
# ---------------------------------------------------------------------------


def load_corpus(
    artifact_root: Path,
    registry: dict,
    footage_keys: list[str] | None = None,
    query_tokens: list[str] | None = None,
) -> dict:
    """Stack ready footages' matrices in stable (registry order, shot_id) order.

    Global row order MUST stay stable across requests so results map back to
    shots. BM25 is stored per footage; each footage scores the query tokens
    with its own index and the raw scores are concatenated for one global
    max-normalization in `score_query` (§3.5).
    """
    keys = [
        k
        for k in registry
        if registry[k].get("state") == "ready"
        and (footage_keys is None or k in footage_keys)
    ]
    visuals, dialogues, captions, metas, bm25_parts = [], [], [], [], []
    for key in keys:
        root = artifact_root / "footage" / key
        try:
            with open(root / "shots.json", encoding="utf-8") as f:
                shots = json_load(f)
            npz = np.load(root / "embeddings.npz")
        except (OSError, ValueError) as exc:
            log.warning("skipping %s (%s)", key, exc)
            continue
        order = sorted(range(len(shots)), key=lambda i: shots[i]["shot_id"])
        visuals.append(npz["visual"][order])
        dialogues.append(npz["dialogue"][order])
        captions.append(npz["caption"][order])
        path = registry[key].get("path", "")
        for i in order:
            s = shots[i]
            metas.append(
                {
                    "footage_key": key,
                    "shot_id": s["shot_id"],
                    "source_path": path,
                    "start_s": s["start_s"],
                    "end_s": s["end_s"],
                    "transcript": s.get("transcript", ""),
                    "caption": s.get("caption", ""),
                    "entities": s.get("entities", []),
                    "text_context": (
                        s.get("transcript", "") + " " + s.get("caption", "")
                    ).strip(),
                }
            )
        bm25_parts.append(_bm25_scores(root, query_tokens or [], len(order)))
    if not metas:
        empty = np.zeros((0, 1), dtype=np.float32)
        return {
            "visual": empty,
            "dialogue": empty,
            "caption": empty,
            "bm25_raw": np.zeros(0),
            "shots": [],
        }
    return {
        "visual": np.vstack(visuals).astype(np.float32),
        "dialogue": np.vstack(dialogues).astype(np.float32),
        "caption": np.vstack(captions).astype(np.float32),
        "bm25_raw": np.concatenate(bm25_parts).astype(float),
        "shots": metas,
    }


def json_load(f):  # type: ignore[no-untyped-def]
    import json

    return json.load(f)


def _bm25_scores(root: Path, tokens: list[str], n: int) -> np.ndarray:
    if not tokens:
        return np.zeros(n)
    try:
        with open(root / "bm25.pkl", "rb") as f:
            index = pickle.load(f)
        return np.asarray(index.get_scores(tokens), dtype=float)
    except (OSError, pickle.PickleError, AttributeError) as exc:
        log.warning("BM25 unreadable for %s (%s)", root, exc)
        return np.zeros(n)
