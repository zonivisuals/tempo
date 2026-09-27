"""Text features: tokenizer, NER cleanup, windows, query entities (notebook cells da236107 / 3de29697)."""

from tempo_engine import textproc


def test_tokenize_strips_punctuation_and_stopwords():
    assert textproc.tokenize("Tokyo, the city of LIGHTS!") == ["tokyo", "city", "lights"]


def test_tokenize_keeps_digits_and_drops_single_letters():
    assert textproc.tokenize("a 7 b 42") == ["7", "42"]


def test_tokenize_cjk_as_bigrams():
    assert textproc.tokenize("東京タワー") == ["東京", "京タ", "タワ", "ワー"]
    assert textproc.tokenize("猫") == ["猫"]


def test_clean_entities_merges_subword_fragments():
    # 'A' + '##kita' used to leak as two entities and 'A' matched every shot.
    text = "Road trip to Akita with Jhon."
    raw = [{"start": 13, "end": 14, "score": 0.9}, {"start": 14, "end": 18, "score": 0.8},
           {"start": 24, "end": 28, "score": 0.95}]
    assert textproc.clean_entities(raw, text, min_score=0.6) == ["Akita", "Jhon"]


def test_clean_entities_drops_junk_and_low_scores():
    text = "A 42 Tokyo"
    raw = [{"start": 0, "end": 1, "score": 0.99}, {"start": 2, "end": 4, "score": 0.99},
           {"start": 5, "end": 10, "score": 0.5}]
    assert textproc.clean_entities(raw, text, min_score=0.6) == []


def test_ner_inputs_skips_blank_texts_and_truncates():
    clipped, idx = textproc.ner_inputs(["", "x" * 2000, "  ", None])
    assert idx == [1]
    assert len(clipped[1]) == textproc.NER_MAX_CHARS


def test_text_in_window_uses_word_timing():
    segs = [{"start": 0.0, "end": 4.0, "text": "hello there old friend",
             "words": [{"word": " hello", "start": 0.0, "end": 0.5},
                       {"word": " there", "start": 0.6, "end": 1.0},
                       {"word": " old", "start": 2.0, "end": 2.4},
                       {"word": " friend", "start": 3.0, "end": 3.5}]},
            {"start": 10.0, "end": 12.0, "text": "later", "words": []}]
    assert textproc.text_in_window(segs, 0.8, 2.5) == "there old"
    assert textproc.text_in_window(segs, 9.0, 11.0) == "later"
    assert textproc.text_in_window(segs, 5.0, 9.0) == ""


def test_bm25_doc_adds_source_dialogue_only_when_translated():
    shot = {"dialogue_en": "good morning", "caption": "a street", "ocr_text": "", "entities": ["Tokyo"],
            "emotions": ["joy"], "dialogue_src": "good morning"}
    assert textproc.bm25_doc(shot) == ["good", "morning", "street", "tokyo", "joy"]
    shot["dialogue_src"] = "ohayou gozaimasu"
    assert textproc.bm25_doc(shot)[-2:] == ["ohayou", "gozaimasu"]


def test_fuzzy_vocab_tolerates_typos_by_length():
    keys = ["john", "akita", "shibuya crossing"]
    assert textproc.fuzzy_vocab("jhon", keys) == "john"  # transposition counts once
    assert textproc.fuzzy_vocab("akitaa", keys) == "akita"
    assert textproc.fuzzy_vocab("shibuya crosing", keys) == "shibuya crossing"
    assert textproc.fuzzy_vocab("joe", keys) is None  # too short to guess
    assert textproc.fuzzy_vocab("berlin", keys) is None


def test_query_entities_resolves_ner_and_ngrams_against_vocab():
    vocab = {"akita": "Akita", "john": "John", "tokyo tower": "Tokyo Tower"}

    def ner(texts):
        as_typed, titled = texts
        return [[] if as_typed == as_typed.lower() else ["Jhon"], ["Akita"] if "Akita" in titled else []]

    assert textproc.query_entities("road trip to akita", vocab, ner) == ["akita"]
    assert textproc.query_entities("Jhon at tokyo tower", vocab, ner) == ["john", "tokyo tower"]


def test_query_entities_trusts_typed_entities_unseen_in_video():
    def ner(texts):
        return [["Berlin"], ["Berlin"]]

    assert textproc.query_entities("Berlin", {}, ner) == ["berlin"]
