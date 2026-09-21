"""P3 verification: pure stage logic (no model weights needed)."""

import numpy as np

from tempo_service.indexer import captions, cluster, ner
from tempo_service.indexer.build_index import bm25_corpus


def test_clean_caption_strips_scaffold_and_repeats():
    raw = "Question: Describe this image. Answer: 'A red van. A red van. A street.'"
    assert captions.clean_caption(raw) == "A red van. A street."


def test_clean_caption_caps_sentences():
    raw = "Answer: One. Two. Three. Four. Five."
    assert captions.clean_caption(raw) == "One. Two. Three."


def test_merge_split_entities_rejoins_fragments():
    raw = [
        {"word": "A", "score": 0.9, "start": 0, "end": 1},
        {"word": "##kita", "score": 0.8, "start": 1, "end": 5},
        {"word": "Tokyo", "score": 0.95, "start": 10, "end": 15},
    ]
    merged = ner.merge_split_entities(raw)
    assert [m["word"] for m in merged] == ["Akita", "Tokyo"]


def test_extract_entities_filters_junk(monkeypatch):
    monkeypatch.setattr(
        ner,
        "_raw_entities",
        lambda text: [
            {"word": "A", "score": 0.99, "start": 0, "end": 1},  # 1-char junk
            {"word": "##x", "score": 0.99, "start": 5, "end": 6},  # orphan fragment
            {"word": "2024", "score": 0.99, "start": 7, "end": 11},  # digits
            {"word": "Japan", "score": 0.99, "start": 12, "end": 17},
            {"word": "japan", "score": 0.9, "start": 20, "end": 25},  # dup, lowercased
            {"word": "Osaka", "score": 0.5, "start": 26, "end": 31},  # under threshold
        ],
    )
    assert ner.extract_entities("junk probe") == ["Japan"]


def test_cluster_small_n_single_group():
    rng = np.random.RandomState(0)
    embs = rng.rand(3, 8).astype(np.float32)
    assert cluster.choose_k(embs) == 0
    labels, reps = cluster.cluster_shots(embs)
    assert set(labels.tolist()) == {0} and reps == [0, 1]


def test_bm25_corpus_shape():
    shots = [
        {"transcript": "Hello world", "caption": "A van", "ocr_text": "", "entities": ["Japan"]},
        {"transcript": "", "caption": "", "ocr_text": "SALE", "entities": []},
    ]
    corpus = bm25_corpus(shots)
    assert corpus[0] == ["hello", "world", "a", "van", "japan"]
    assert corpus[1] == ["sale"]
