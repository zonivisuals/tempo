"""Index build: 3x FAISS + BM25 (UMAP excluded — visualization-only).

Mechanical port of `tempo_pipeline_v3.ipynb` cell 8241b95a — the notebook is the
behavioral reference; this module is the deployable one. Bodies below are
verbatim except the logged deviations. Re-verify against the notebook on any
pipeline change (golden + parity tests guard drift).

Deviations from verbatim:
  - UMAP block DROPPED (AGENTS §3.5: visualization-only, notebook-only);
  - build_search_indices RETURNS its products instead of writing
    notebook globals (deployable, per-footage safe);
  - _need() guards at entries.
"""
import numpy as np

from . import _deps
from ._deps import _need

try:
    import faiss
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("faiss-cpu", _err)
    faiss = None  # type: ignore[no-redef,assignment]

try:
    from rank_bm25 import BM25Okapi
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("rank-bm25", _err)
    BM25Okapi = None  # type: ignore[no-redef,assignment]

def _build_faiss(emb_matrix):
    """L2-normalised inner-product index (= cosine similarity)."""
    idx = faiss.IndexFlatIP(emb_matrix.shape[1])
    idx.add(emb_matrix)
    return idx


def build_search_indices(shots):
    """
    Three FAISS indexes (returned; notebook kept globals) — one per key type. Built but not queried at search
    time (search_tempo uses direct matmul for shot-aligned scores); kept for
    a future FAISS-based retrieval path.
    """
    _need(faiss, "faiss-cpu")
    _need(BM25Okapi, "rank-bm25")
    vis_mat  = np.array([s["visual_embedding"]   for s in shots], dtype=np.float32)
    dial_mat = np.array([s["dialogue_embedding"]  for s in shots], dtype=np.float32)
    cap_mat  = np.array([s["caption_embedding"]   for s in shots], dtype=np.float32)

    faiss_visual = _build_faiss(vis_mat)
    faiss_dialog = _build_faiss(dial_mat)
    faiss_cap    = _build_faiss(cap_mat)
    print(f"FAISS: 3 indexes built ({faiss_visual.ntotal} shots each).")

    # BM25 — transcript + caption + OCR + entities (emotions dropped, parity).
    corpus = []
    for s in shots:
        doc = (f"{s.get('transcript','')} {s.get('caption','')} {s.get('ocr_text','')} "
               f"{chr(32).join(s.get('entities', []))}")
        corpus.append(doc.lower().split())
    bm25_index = BM25Okapi(corpus)
    print(f"BM25: {len(shots)} docs.")
    return {
        "visual": vis_mat,
        "dialogue": dial_mat,
        "caption": cap_mat,
        "bm25": bm25_index,
        "faiss": {"visual": faiss_visual, "dialogue": faiss_dialog, "caption": faiss_cap},
    }
