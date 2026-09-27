"""Search corpus: merged indexes + FAISS + exact key statistics, cached per content set.

Built from one or more `TempoIndex` objects in a stable order (the caller's
content order, then shot order). Rows are global; FAISS ids map back to those
rows by construction (flat indexes are added in row order; the dialogue index
is an IndexIDMap over the D_mask rows) — AGENTS.md §3.5.

`CorpusCache` keeps the last `corpus_cache_size` content sets, keyed by
(content_id, index.json mtime) pairs: rebuilding an index invalidates every
set that contains it without any explicit bookkeeping.
"""

import logging
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np

from . import textproc
from .index import INDEX_JSON, TempoIndex
from .search import Bm25Postings, KeyStats

log = logging.getLogger("tempo.engine.corpus")


def _flat(M: np.ndarray):  # type: ignore[no-untyped-def]
    import faiss

    index = faiss.IndexFlatIP(M.shape[1])
    if len(M):
        index.add(np.ascontiguousarray(M, np.float32))
    return index


def _masked(M: np.ndarray, mask: np.ndarray):  # type: ignore[no-untyped-def]
    import faiss

    index = faiss.IndexIDMap(faiss.IndexFlatIP(M.shape[1]))
    rows = np.nonzero(mask)[0]
    if len(rows):
        index.add_with_ids(np.ascontiguousarray(M[rows], np.float32), rows.astype(np.int64))
    return index


class Corpus:
    def __init__(self, indexes: list[TempoIndex]) -> None:
        from rank_bm25 import BM25Okapi

        self.indexes = indexes
        self.rows: list[tuple[TempoIndex, int]] = [(ix, i) for ix in indexes for i in range(len(ix.shots))]
        self.n = len(self.rows)
        dims = [(ix.V.shape[1], ix.D.shape[1]) for ix in indexes]
        v_dim, t_dim = dims[0] if dims else (1, 1)
        self.V = np.vstack([ix.V for ix in indexes]).astype(np.float32) if indexes else np.zeros((0, v_dim))
        self.D = np.vstack([ix.D for ix in indexes]).astype(np.float32) if indexes else np.zeros((0, t_dim))
        self.C = np.vstack([ix.C for ix in indexes]).astype(np.float32) if indexes else np.zeros((0, t_dim))
        self.D_mask = np.concatenate([ix.D_mask for ix in indexes]) if indexes else np.zeros(0, bool)
        shots = [ix.shots[i] for ix, i in self.rows]
        self.caption_conf = np.array([s["caption_conf"] for s in shots], np.float32)
        self.scene_keys = [(ix.content_id, ix.shots[i]["scene_id"]) for ix, i in self.rows]
        self.shot_entities = [{e.lower() for e in s["entities"]} for s in shots]
        self.shot_texts = [f'{s["dialogue_en"]} {s["ocr_text"]}'.lower() for s in shots]
        docs = [textproc.bm25_doc(s) for s in shots]
        self.bm25 = Bm25Postings(BM25Okapi(docs)) if any(docs) else None
        self.vocab: dict[str, str] = {}
        for ix in indexes:
            for k, v in ix.vocab.items():
                self.vocab.setdefault(k, v)
        self.faiss_visual = _flat(self.V)
        self.faiss_caption = _flat(self.C)
        self.faiss_dialogue = _masked(self.D, self.D_mask)
        self.stats_visual = KeyStats.of(self.V)
        self.stats_dialogue = KeyStats.of(self.D, self.D_mask)
        self.stats_caption = KeyStats.of(self.C)

    def shot(self, row: int) -> tuple[TempoIndex, dict]:
        ix, i = self.rows[row]
        return ix, ix.shots[i]


class CorpusCache:
    def __init__(self, size: int) -> None:
        self.size = max(1, size)
        self._sets: OrderedDict[tuple, Corpus] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(dirs: list[Path]) -> tuple:
        return tuple((d.name, (d / INDEX_JSON).stat().st_mtime_ns) for d in dirs)

    def get(self, dirs: list[Path]) -> Corpus:
        key = self._key(dirs)
        with self._lock:
            hit = self._sets.get(key)
            if hit is not None:
                self._sets.move_to_end(key)
                return hit
        corpus = Corpus([TempoIndex.load(d) for d in dirs])
        log.info("corpus built: %d contents, %d shots", len(dirs), corpus.n)
        with self._lock:
            self._sets[key] = corpus
            self._sets.move_to_end(key)
            while len(self._sets) > self.size:
                self._sets.popitem(last=False)
        return corpus
