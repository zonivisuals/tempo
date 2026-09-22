"""Modal backend contract (ADR-0004).

- Extracted stages import on CPU without heavy deps; guarded entries raise
  ImportError naming the pip package (never a bare AttributeError).
- CPU-testable pure functions behave per the notebook (caption clean,
  entity merge/filter, text alignment).
- modal_backend/scoring.py is parity-locked to service.search.score_query:
  identical fixtures must produce identical finals, winners, contributions.
- modal_api.py lifecycle (fake runner/embed, tmp dirs): auth, index -> poll
  -> done with checkpoints + artifacts, search shape, thumbs, error codes.
- pipeline.run_all orchestration with faked stages writes real artifacts.

modal_backend/ lives at repo root, outside service/ — hence the sys.path
pin below (mirrors how the Modal image adds the repo root).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _PicklableBM25:
    """Module level so pickle works (local classes cannot pickle)."""

    def __init__(self, score=1.0):
        self.score = score

    def get_scores(self, tokens):
        return [self.score]


def test_stages_import_clean_and_guards_name_packages():
    import modal_backend.audio_ocr as ao
    import modal_backend.enrich as en
    import modal_backend.indices as ix
    import modal_backend.ner as ner
    import modal_backend.shots_visual as sv
    import modal_backend.singletons as sg

    cases = [
        (sv.extract_shots_and_keyframes, ("x.mp4",), "scenedetect"),
        (sv.get_visual_embeddings_and_cluster, ([],), "torch"),
        (ao.transcribe_audio, ("x.mp4",), "faster-whisper"),
        (sg._get_ner_pipeline, (), "transformers"),
        (en.enrich_with_local_models, ([],), "torch"),
        (ix.build_search_indices, ([],), "faiss-cpu"),
    ]
    for fn, args, pip in cases:
        try:
            fn(*args)
            raise AssertionError(f"{fn.__name__} should need {pip}")
        except ImportError as exc:
            assert pip in str(exc), f"{fn.__name__}: {exc}"


def test_pure_functions_match_notebook_behavior():
    from modal_backend import enrich as en
    from modal_backend import ner as ner_mod
    from modal_backend.audio_ocr import assign_text_to_shots

    assert en._clean_caption("Question: Describe this image. Answer: A cat. A cat.") == "A cat."
    assert en._clean_caption("Answer: One. Two. Three. Four.") == "One. Two. Three."
    assert ner_mod._extract_entities("") == []
    assert ner_mod._extract_entities("   ") == []
    merged = ner_mod._merge_split_entities(
        [
            {"word": "A", "start": 0, "end": 1, "score": 0.9},
            {"word": "##kita", "start": 1, "end": 5, "score": 0.9},
        ]
    )
    assert merged == [{"word": "Akita", "start": 0, "end": 5, "score": 0.9}]

    shots = [{"shot_id": 0, "start_time": 0.0, "end_time": 2.0, "ocr_text": "hi"}]
    segs = [{"start": 0.5, "end": 1.5, "text": "hello world",
             "words": [{"word": "hello", "start": 0.5, "end": 1.0}]}]
    assign_text_to_shots(shots, segs)
    assert shots[0]["transcript"] == "hello"
    assert shots[0]["text_context"] == "hello hi"


def test_scoring_parity_with_service():
    from modal_backend import scoring as modal_scoring
    from tempo_service import search as service_search

    rng = np.random.default_rng(7)
    n, d = 9, 16

    def normed(*shape):
        m = rng.normal(size=shape).astype("float32")
        return m / np.linalg.norm(m, axis=-1, keepdims=True)

    q = normed(d)
    visual, dialogue, caption = normed(n, d), normed(n, d), normed(n, d)
    bm25 = np.abs(rng.normal(size=n))
    qe = ["Japan", "A"]
    shot_ents = [["Japan"], [], ["a"], [], [], [], [], [], []]
    ctxs = ["tokyo japan", "plain", "a letter", "x", "y", "z", "w", "v", "u"]

    kw = dict(dense_w=0.45, bm25_w=0.40, anchor_w=0.15, entity_boost=0.15)
    a = service_search.score_query(q, visual, dialogue, caption, bm25, qe, shot_ents, ctxs, **kw)
    b = modal_scoring.score_query(q, visual, dialogue, caption, bm25, qe, shot_ents, ctxs, **kw)
    for key in ("final", "key_stack", "dense_c", "bm25_c", "anchor_c", "boost"):
        assert np.allclose(a[key], b[key]), key
    assert (a["winner"] == b["winner"]).all()


def _api(tmp_path, **kw):
    from modal_backend.modal_api import create_app
    from fastapi.testclient import TestClient

    art = tmp_path / "art"
    ckpt = tmp_path / "ckpt"
    art.mkdir(exist_ok=True)
    ckpt.mkdir(exist_ok=True)
    return TestClient(create_app(auth_token="sekret", artifacts_root=art,
                                 checkpoint_root=ckpt, **kw)), art, ckpt


def _fake_run_all_factory(art_dir_holder):
    def fake_run_all(src, out_dir, progress):
        import numpy as _np

        out = Path(out_dir)
        (out / "thumbs").mkdir(parents=True, exist_ok=True)
        (out / "thumbs" / "keyframe_0.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        shots = [{"shot_id": 0, "start_s": 0.0, "end_s": 1.0, "transcript": "hello",
                  "caption": "a van", "ocr_text": "", "entities": [], "cluster_id": 0}]
        (out / "shots.json").write_text(json.dumps(shots))
        z = _np.zeros((1, 4), dtype=_np.float32)
        _np.savez_compressed(out / "embeddings.npz", visual=z, dialogue=z, caption=z)

        import pickle

        (out / "bm25.pkl").write_bytes(pickle.dumps(_PicklableBM25(1.0)))
        progress("shots", 1, 1)
        return {"shot_count": 1, "duration_s": 1.0}

    return fake_run_all


def test_modal_api_lifecycle_and_search(tmp_path):
    client, art, ckpt = _api(
        tmp_path,
        run_all=_fake_run_all_factory(None),
        embed_query=lambda q: np.zeros(4, dtype=np.float32),
        resolve_source=lambda ref: Path("/nonexistent") / ref,
    )
    h = {"Authorization": "Bearer sekret"}

    assert client.get("/health").json() == {"status": "ok", "gpu": False}
    assert client.post("/index", json={"drive_path": "tempo/k/a.mp4"}).status_code == 401
    assert client.post("/index", json={"drive_path": ""}, headers=h).status_code == 400
    assert client.get("/jobs/nope", headers=h).status_code == 404

    # source missing on the "volume" -> honest job error naming the location
    jid = client.post("/index", json={"drive_path": "tempo/k/a.mp4"}, headers=h).json()["job_id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        st = client.get(f"/jobs/{jid}", headers=h).json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert st["state"] == "error"
    assert "tempo/k/a.mp4" in st["error"]
    assert (ckpt / "k").is_dir()  # checkpoints written even on failure paths

    # now stage the file where the resolver points and re-index -> done
    real = tmp_path / "vol" / "k"
    real.mkdir(parents=True)
    (real / "a.mp4").write_bytes(b"\x00" * 16)
    client2, art2, ckpt2 = _api(
        tmp_path,
        run_all=_fake_run_all_factory(None),
        embed_query=lambda q: np.zeros(4, dtype=np.float32),
        resolve_source=lambda ref: tmp_path / "vol" / ref.split("tempo/")[-1],
    )
    jid = client2.post("/index", json={"drive_path": "tempo/k/a.mp4"}, headers=h).json()["job_id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        st = client2.get(f"/jobs/{jid}", headers=h).json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert st["state"] == "done", st
    assert st["shot_count"] == 1
    assert len(st["stages"]) == 10
    assert all(s["state"] == "done" for s in st["stages"])

    body = client2.get("/search", params={"q": "van"}, headers=h).json()
    assert body["query"] == "van" and len(body["results"]) == 1
    r = body["results"][0]
    assert r["source_path"] == ""  # service backfills from its registry
    assert set(r) >= {"footage_key", "shot_id", "score", "winning_key", "raw_cos",
                      "contributions", "transcript", "caption", "entities"}
    assert client2.get("/search", params={"q": "x", "footage_keys": "nope"},
                       headers=h).json()["results"] == []

    t = client2.get("/thumb/k/0.jpg", headers=h)
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg"
    assert client2.get("/thumb/k/9.jpg", headers=h).status_code == 404


def test_modal_api_search_empty_corpus_needs_no_model(tmp_path):
    client, _, _ = _api(tmp_path, embed_query=None)
    h = {"Authorization": "Bearer sekret"}
    r = client.get("/search", params={"q": "van"}, headers=h)
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_modal_api_search_without_model_is_503(tmp_path):
    import pickle

    client, art, _ = _api(tmp_path, embed_query=None)
    h = {"Authorization": "Bearer sekret"}
    root = art / "k"
    (root / "thumbs").mkdir(parents=True)
    root.joinpath("shots.json").write_text(json.dumps(
        [{"shot_id": 0, "start_s": 0.0, "end_s": 1.0, "transcript": "hi",
          "caption": "a van", "ocr_text": "", "entities": [], "cluster_id": 0}]))
    np.savez_compressed(root / "embeddings.npz",
                        visual=np.zeros((1, 4), dtype=np.float32),
                        dialogue=np.zeros((1, 4), dtype=np.float32),
                        caption=np.zeros((1, 4), dtype=np.float32))

    root.joinpath("bm25.pkl").write_bytes(pickle.dumps(_PicklableBM25(1.0)))
    r = client.get("/search", params={"q": "van"}, headers=h)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "MODEL_NOT_LOADED"


def test_pipeline_orchestration_writes_artifacts(tmp_path, monkeypatch):
    import modal_backend.pipeline as pl

    def fake_shots(src, out_dir):
        from pathlib import Path as _P

        _P(out_dir).mkdir(parents=True, exist_ok=True)
        (_P(out_dir) / "keyframe_0.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        return [{"shot_id": 0, "start_time": 0.0, "end_time": 2.0}]

    def fake_cluster(shots):
        for s in shots:
            s["cluster_id"] = 0
            s["is_cluster_rep"] = True
            s["visual_embedding"] = [0.0, 1.0]

    def fake_transcribe(src):
        return [{"start": 0.0, "end": 2.0, "text": "hi",
                 "words": [{"word": "hi", "start": 0.1, "end": 0.4}]}]

    def fake_ocr(shots):
        for s in shots:
            s["ocr_text"] = ""

    def fake_enrich(shots):
        import numpy as _np

        for s in shots:
            s["caption"] = "a cat"
            s["entities"] = []
            s["emotions"] = []
            s["dialogue_embedding"] = _np.zeros(2, dtype=_np.float32)
            s["caption_embedding"] = _np.zeros(2, dtype=_np.float32)

    def fake_build(shots):
        import numpy as _np

        return {"visual": _np.zeros((1, 2), dtype=_np.float32),
                "dialogue": _np.zeros((1, 2), dtype=_np.float32),
                "caption": _np.zeros((1, 2), dtype=_np.float32),
                "bm25": _PicklableBM25(0.0), "faiss": {}}

    monkeypatch.setattr(pl.shots_visual, "extract_shots_and_keyframes", fake_shots)
    monkeypatch.setattr(pl.shots_visual, "get_visual_embeddings_and_cluster", fake_cluster)
    monkeypatch.setattr(pl.audio_ocr, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(pl.audio_ocr, "extract_ocr_text", fake_ocr)
    monkeypatch.setattr(pl.audio_ocr, "assign_text_to_shots",
                        pl.audio_ocr.assign_text_to_shots)  # real alignment
    monkeypatch.setattr(pl.enrich, "enrich_with_local_models", fake_enrich)
    monkeypatch.setattr(pl.indices, "build_search_indices", fake_build)

    src = tmp_path / "v.mp4"
    src.write_bytes(b"\x00" * 8)
    out = tmp_path / "out"
    seen = []
    summary = pl.run_all(src, out, lambda st, d, t: seen.append((st, d, t)))
    assert summary == {"shot_count": 1, "duration_s": 2.0}
    assert (out / "shots.json").is_file()
    assert (out / "embeddings.npz").is_file()
    assert (out / "bm25.pkl").is_file()
    assert (out / "thumbs" / "keyframe_0.jpg").is_file()
    stages = [s for s, _, _ in seen]
    assert "shots" in stages and "build_index" in stages
    lite = json.loads((out / "shots.json").read_text())
    assert lite[0]["transcript"] == "hi"  # real assign_text_to_shots ran
