"""Tier 1 — on-screen text (EasyOCR).

Port of notebook cell b9ae1b9d (`EASYOCR_LANG`, `_edge_fraction`, `run_ocr`):
full frame (subtitles and lower thirds live at the bottom), sequential,
confidence-filtered, language-matched reader.

Deviations from the notebook:
  - progress = keyframes processed;
  - weights live under `<data_root>/easyocr` (the persistent volume) instead
    of the home directory.
"""

import logging

from .. import models
from ..cache import StageCache
from ..config import settings
from . import Progress

log = logging.getLogger("tempo.engine.ocr")

# Whisper language code -> EasyOCR code. English is compatible with every EasyOCR language.
EASYOCR_LANG = {"ar": "ar", "ja": "ja", "ko": "ko", "zh": "ch_sim", "fr": "fr", "es": "es", "de": "de",
                "it": "it", "pt": "pt", "ru": "ru", "tr": "tr", "hi": "hi", "fa": "fa", "ur": "ur",
                "nl": "nl", "id": "id", "vi": "vi", "th": "th", "pl": "pl", "uk": "uk"}
EASYOCR_DIR = "easyocr"
MIN_TEXT_LEN = 2


def _edge_fraction(frame) -> float:  # type: ignore[no-untyped-def]
    import cv2

    return float((cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 100, 200) > 0).mean())


def _reader(langs: list[str]):  # type: ignore[no-untyped-def]
    import easyocr

    store = settings.data_root / EASYOCR_DIR
    store.mkdir(parents=True, exist_ok=True)
    return easyocr.Reader(langs, gpu=models.gpu(), verbose=False, model_storage_directory=str(store))


def run_ocr(shots: list[dict], cache: StageCache, language: str, progress: Progress) -> list[str]:
    import cv2

    langs = ["en"] + ([EASYOCR_LANG[language]] if language in EASYOCR_LANG and language != "en" else [])
    try:
        reader = _reader(langs)
    except Exception as ex:
        log.warning("EasyOCR %s unavailable (%s); using English only.", langs, ex)
        reader = _reader(["en"])

    texts, skipped = [], 0
    progress(0, len(shots))
    for i, s in enumerate(shots):
        frame = cv2.imread(cache.abs(s["keyframe_path"]))
        if frame is None or _edge_fraction(frame) < settings.ocr_edge_min:
            texts.append("")
            skipped += 1
        else:
            found = [t.strip() for _, t, conf in reader.readtext(frame, detail=1, paragraph=False)
                     if conf >= settings.ocr_min_conf and len(t.strip()) >= MIN_TEXT_LEN]
            texts.append(" ".join(dict.fromkeys(found)))
        progress(i + 1, len(shots))
    del reader
    models.free_memory()
    log.info("OCR [%s]: %d frames read, %d skipped as flat, %d contain text",
             "+".join(langs), len(shots) - skipped, skipped, sum(1 for t in texts if t))
    return texts
