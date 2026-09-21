"""Stage 4 `transcribe`: faster-whisper large-v3, word timestamps.

CTranslate2 backend (`float16` on CUDA, `int8` on CPU). Non-English audio
gets a second `translate` pass; the translation is stored alongside so
nothing downstream changes shape. Word-level alignment into shots with
segment-overlap fallback (research artifact).
"""

import logging

log = logging.getLogger("tempo.audio")


def transcribe(video_path: str) -> tuple[list[dict], str]:
    """Returns (segments, language). Segments carry words + optional translation."""
    from faster_whisper import WhisperModel

    from .models import load

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    def factory():  # type: ignore[no-untyped-def]
        from .config import settings

        return WhisperModel(settings.whisper_model_name, device=device, compute_type=compute)

    model = load("whisper", factory)
    segments_gen, info = model.transcribe(video_path, word_timestamps=True)
    lang = info.language
    log.info("transcribe: language=%s", lang)

    segments = []
    for seg in segments_gen:
        segments.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end} for w in (seg.words or [])
                ],
            }
        )
    if lang != "en":
        segs_en, _ = model.transcribe(video_path, task="translate", word_timestamps=True)
        for seg_o, seg_e in zip(segments, segs_en):
            seg_o["translated_text"] = seg_e.text
    log.info("transcribe: %d segments", len(segments))
    return segments, lang


def assign_text_to_shots(shots: list[dict], segments: list[dict]) -> None:
    """Word-level transcript per shot; `text_context` = transcript + OCR (set later)."""
    for shot in shots:
        words = []
        for seg in segments:
            if seg.get("words"):
                for w in seg["words"]:
                    ws = w.get("start", seg["start"])
                    we = w.get("end", seg["end"])
                    if ws < shot["end_s"] and we > shot["start_s"]:
                        words.append(w["word"].strip())
            elif seg["start"] <= shot["end_s"] and seg["end"] >= shot["start_s"]:
                words.append(seg["text"].strip())
        shot["transcript"] = " ".join(words).strip()
    for shot in shots:
        shot["text_context"] = (shot.get("transcript", "") + " " + shot.get("ocr_text", "")).strip()
