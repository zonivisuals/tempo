"""Tier 1: faster-whisper transcription, EasyOCR, text-to-shot alignment.

Mechanical port of `tempo_pipeline_v3.ipynb` cell 6fd10aa2 — the notebook is the
behavioral reference; this module is the deployable one. Bodies below are
verbatim except the logged deviations. Re-verify against the notebook on any
pipeline change (golden + parity tests guard drift).

Deviations from verbatim:
  - cross-cell names become explicit imports via ._deps;
  - EasyOCR keeps its function-level import (honest ModuleNotFoundError);
  - `del x; gc.collect(); …` semicolons kept verbatim (ruff E702 exempt file-wide);
  - _need() guards at entries.
"""
# ruff: noqa: E702
import concurrent.futures
import gc

from . import _deps
from ._deps import _need

try:
    import cv2
except ImportError:  # CPU/test host: guarded, _need() explains at call
    cv2 = None  # type: ignore[no-redef,assignment]

try:
    from faster_whisper import WhisperModel
except ImportError:  # CPU/test host: guarded, _need() explains at call
    WhisperModel = None  # type: ignore[no-redef,assignment]

try:
    import torch
except ImportError:  # CPU/test host: guarded, _need() explains at call
    torch = None  # type: ignore[no-redef,assignment]
DEVICE = _deps.device()

def transcribe_audio(video_path, model_size="large-v3"):
    """
    faster-whisper (CTranslate2 backend). Word-level timestamps preserved.
    Returns the same segment list shape as before so nothing downstream changes.
    """
    _need(WhisperModel, "faster-whisper")
    compute = "float16" if DEVICE == "cuda" else "int8"
    fw      = WhisperModel(model_size, device=DEVICE, compute_type=compute)

    segments_gen, info = fw.transcribe(video_path, word_timestamps=True)
    lang = info.language
    print(f"Detected language: {lang}")

    segments = []
    for seg in segments_gen:
        words = [
            {"word": w.word, "start": w.start, "end": w.end}
            for w in (seg.words or [])
        ]
        segments.append({
            "start": seg.start, "end": seg.end,
            "text":  seg.text,  "words": words,
        })

    if lang != "en":
        segs_en, _ = fw.transcribe(video_path, task="translate", word_timestamps=True)
        for seg_o, seg_e in zip(segments, segs_en):
            seg_o["translated_text"] = seg_e.text

    del fw; gc.collect(); torch.cuda.empty_cache()
    print(f"Transcription done ({len(segments)} segments).")
    return segments


def _has_text_likelihood(frame_bgr, threshold=0.04):
    _need(cv2, "opencv-python")
    h, w = frame_bgr.shape[:2]
    roi  = frame_bgr[h // 5: 4 * h // 5, w // 10: 9 * w // 10]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return cv2.Canny(gray, 100, 200).mean() > threshold


def _ocr_one(args):
    """Worker for parallel OCR. Runs in a thread (EasyOCR releases the GIL)."""
    reader, kf = args
    if not _has_text_likelihood(kf["frame_bgr"]):
        return kf["shot_id"], ""
    results = reader.readtext(kf["keyframe_path"], detail=0, paragraph=True)
    return kf["shot_id"], " ".join(results)


def extract_ocr_text(keyframes, workers=4):
    """
    Parallel OCR with edge-density pre-filter. Uses in-memory frame_bgr
    instead of re-reading from disk.
    """
    import easyocr
    reader  = easyocr.Reader(["en"], gpu=(DEVICE == "cuda"))
    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_ocr_one, (reader, kf)): kf["shot_id"] for kf in keyframes}
        for done in concurrent.futures.as_completed(futures):
            sid, text = done.result()
            results[sid] = text

    for kf in keyframes:
        kf["ocr_text"] = results.get(kf["shot_id"], "")

    skipped = sum(1 for v in results.values() if v == "")
    del reader; gc.collect(); torch.cuda.empty_cache()
    print(f"OCR done. Skipped {skipped}/{len(keyframes)} frames.")


def assign_text_to_shots(shots, whisper_segments):
    """Word-level alignment, segment-overlap fallback."""
    for shot in shots:
        words = []
        for seg in whisper_segments:
            for w in seg.get("words", []):
                ws = w.get("start", seg["start"])
                we = w.get("end",   seg["end"])
                if ws < shot["end_time"] and we > shot["start_time"]:
                    words.append(w["word"].strip())
            if not seg.get("words"):
                if seg["start"] <= shot["end_time"] and seg["end"] >= shot["start_time"]:
                    words.append(seg["text"].strip())
        shot["transcript"]   = " ".join(words).strip()
        shot["text_context"] = shot["transcript"] + " " + shot.get("ocr_text", "")