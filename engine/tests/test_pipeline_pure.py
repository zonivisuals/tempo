"""CPU-testable pieces of the pipeline: cache, fingerprint, shot spans, captions, text rows, index I/O."""

import numpy as np
import pytest

from tempo_engine import fingerprint, pipeline
from tempo_engine.cache import StageCache
from tempo_engine.config import CPU_DEFAULTS, GPU_DEFAULTS, EngineSettings, config_signature, profile
from tempo_engine.index import TempoIndex
from tempo_engine.stages import captions, shots, text


def test_stage_cache_hits_and_misses_by_deps(tmp_path):
    cache = StageCache(tmp_path)
    calls = []

    def build():
        calls.append(1)
        return {"n": len(calls)}

    assert cache.stage("shots", {"v": 1}, build) == {"n": 1}
    assert cache.stage("shots", {"v": 1}, build) == {"n": 1}  # resumed, not recomputed
    assert cache.stage("shots", {"v": 2}, build) == {"n": 2}  # dependency changed
    assert cache.has("shots", {"v": 1}) and not cache.has("shots", {"v": 3})


def test_stage_cache_rebuilds_a_torn_file(tmp_path):
    cache = StageCache(tmp_path)
    cache.path("ocr", {}).write_bytes(b"not a pickle")
    assert cache.stage("ocr", {}, lambda: ["x"]) == ["x"]


def test_content_id_small_and_large_files(tmp_path):
    small = tmp_path / "a.bin"
    small.write_bytes(b"abc")
    big = tmp_path / "b.bin"
    big.write_bytes(b"\0" * (fingerprint.CHUNK_BYTES + 10) + b"tail")
    ids = {fingerprint.content_id(small), fingerprint.content_id(big)}
    assert len(ids) == 2 and all(fingerprint.valid(i) for i in ids)
    # Middle bytes are not hashed (fast path); tail bytes are.
    mid = tmp_path / "c.bin"
    mid.write_bytes(b"\0" * 10 + b"\1" * (fingerprint.CHUNK_BYTES * 2) + b"tail")
    before = fingerprint.content_id(mid)
    data = bytearray(mid.read_bytes())
    data[-1] = ord("X")
    mid.write_bytes(bytes(data))
    assert fingerprint.content_id(mid) != before
    assert not fingerprint.valid("../etc") and not fingerprint.valid("ABCDEF0123456789")


def test_profile_resolves_device_defaults_and_overrides():
    s = EngineSettings(whisper_model="large-v3-turbo", caption_budget=7)
    gpu, cpu = profile(s, True), profile(s, False)
    assert gpu.visual_model == GPU_DEFAULTS["visual_model"]
    assert cpu.caption_model == CPU_DEFAULTS["caption_model"]
    assert gpu.whisper_translate_model == "large-v3-turbo" and gpu.caption_budget == 7


def test_signature_excludes_weights():
    a, b = EngineSettings(), EngineSettings(w_visual=0.9, faiss_candidates=8)
    assert config_signature(a, profile(a, True)) == config_signature(b, profile(b, True))
    c = EngineSettings(max_shot_sec=4.0)
    assert config_signature(a, profile(a, True)) != config_signature(c, profile(c, True))


def test_source_cached_needs_shots_and_transcribe(tmp_path):
    prof = profile(EngineSettings(), False)
    assert not pipeline.source_cached("0" * 16, tmp_path, prof)
    deps = pipeline._deps("0" * 16, prof)
    cache = StageCache(tmp_path)
    cache.stage("shots", deps["shots"], lambda: {})
    assert not pipeline.source_cached("0" * 16, tmp_path, prof)
    cache.stage("transcribe", deps["transcribe"], lambda: {})
    assert pipeline.source_cached("0" * 16, tmp_path, prof)


def test_split_spans_caps_long_takes():
    spans = shots.split_spans([(0.0, 20.0), (20.0, 23.0)], max_shot_sec=8.0)
    assert [(round(s, 3), round(e, 3), sc) for s, e, sc in spans] == [
        (0.0, 6.667, 0), (6.667, 13.333, 0), (13.333, 20.0, 0), (20.0, 23.0, 1)]
    assert shots.split_spans([(0.0, 8.0)], 8.0) == [(0.0, 8.0, 0)]


def test_clean_caption_strips_tags_and_dedupes():
    raw = "<s>A man walks. A man walks. He carries a bag! It rains. Extra.</s>"
    assert captions.clean_caption(raw) == "A man walks. He carries a bag! It rains."


def test_caption_propagation_keeps_confidence():
    V = np.eye(3, dtype=np.float32)[[0, 0, 1, 2]]
    V[1] = [0.8, 0.6, 0.0]
    out = captions.propagate(V, [0, 2], ["a dog", "a car"])
    assert out["caption"] == ["a dog", "a dog", "a car", "a dog"]
    assert out["caption_conf"][:3] == pytest.approx([1.0, 0.8, 1.0])
    assert captions.pick_reps(V, 10) == [0, 1, 2, 3]


def test_shot_rows_windows_entities_and_dialogue_mask():
    shots_ = [{"start_time": 0.0, "end_time": 2.0}, {"start_time": 20.0, "end_time": 22.0}]
    asr = {"language": "en",
           "src": [{"start": 0.0, "end": 2.0, "text": "we drive to akita now",
                    "words": [{"word": f" {w}", "start": i * 0.4, "end": i * 0.4 + 0.3}
                              for i, w in enumerate("we drive to akita now".split())]}],
           "en": [{"start": 0.0, "end": 2.0, "text": "we drive to akita now", "words": []}]}
    rows, vocab = text.shot_rows(shots_, asr, ["", "AKITA 5km"], [["Akita"]], [[], ["AKITA", "Akita"]])
    assert vocab == {"akita": "Akita"}
    assert rows[0]["transcript"] == "we drive to akita now"
    assert rows[0]["has_dialogue"] and not rows[1]["has_dialogue"]
    assert rows[0]["entities"] == ["Akita"] and rows[1]["entities"] == ["Akita"]


def test_index_round_trip_and_thumbs(tmp_path):
    from PIL import Image

    (tmp_path / "frames").mkdir()
    Image.new("RGB", (640, 360), (10, 20, 30)).save(tmp_path / "frames" / "k.jpg")
    shot = {"shot_id": 0, "scene_id": 0, "start_time": 0.0, "end_time": 1.0, "duration": 1.0,
            "keyframe_path": "frames/k.jpg", "frame_paths": ["frames/k.jpg"]}
    arrays = {"V": np.ones((1, 4), np.float32), "D": np.zeros((1, 3), np.float32),
              "D_mask": np.array([False]), "C": np.ones((1, 3), np.float32)}
    idx = TempoIndex(tmp_path, {"content_id": "0" * 16, "signature": "s"}, [shot], {}, arrays)
    ticks = []
    idx.write_thumbs(lambda d, t: ticks.append((d, t)))
    idx.save()
    assert ticks[-1] == (1, 1)
    with Image.open(idx.thumb(0)) as im:
        assert im.size == (320, 180)
    back = TempoIndex.load(tmp_path)
    assert back.content_id == "0" * 16 and back.D_mask.dtype == bool
    assert TempoIndex.exists(tmp_path) and TempoIndex.read_meta(tmp_path)["signature"] == "s"
