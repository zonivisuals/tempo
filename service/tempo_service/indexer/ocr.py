"""Stage 5 `ocr`: EasyOCR with edge-density prefilter (AGENTS.md §3.2).

Frames unlikely to contain text (Canny edge density ≤ 0.04 on the center ROI)
are skipped without invoking the reader. ThreadPool(4) — EasyOCR releases
the GIL. OCR runs on the saved keyframes (in-memory BGR retained by shots).
"""

import concurrent.futures
import logging

EDGE_THRESHOLD = 0.04
WORKERS = 4

log = logging.getLogger("tempo.ocr")


def has_text_likelihood(frame_bgr) -> bool:  # type: ignore[no-untyped-def]
    import cv2

    h, w = frame_bgr.shape[:2]
    roi = frame_bgr[h // 5 : 4 * h // 5, w // 10 : 9 * w // 10]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return cv2.Canny(gray, 100, 200).mean() > EDGE_THRESHOLD


def extract_ocr(shots: list[dict], progress=None) -> None:  # type: ignore[no-untyped-def]
    """Fills `ocr_text` per shot (in place); refreshes `text_context`."""
    import cv2
    import torch

    from .models import load

    def factory():  # type: ignore[no-untyped-def]
        import easyocr

        device = "cuda" if torch.cuda.is_available() else "cpu"
        return easyocr.Reader(["en"], gpu=(device == "cuda"))

    reader = load("easyocr", factory)

    def one(shot: dict) -> tuple[int, str]:
        frame = cv2.imread(shot["keyframe"])
        if frame is None or not has_text_likelihood(frame):
            return shot["shot_id"], ""
        results = reader.readtext(shot["keyframe"], detail=0, paragraph=True)
        return shot["shot_id"], " ".join(results)

    texts: dict[int, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(one, shot): shot for shot in shots}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            sid, text = fut.result()
            texts[sid] = text
            done += 1
            if progress is not None:
                progress("ocr", done, len(shots))

    skipped = 0
    for shot in shots:
        shot["ocr_text"] = texts.get(shot["shot_id"], "")
        if not shot["ocr_text"]:
            skipped += 1
        shot["text_context"] = (
            shot.get("transcript", "") + " " + shot.get("ocr_text", "")
        ).strip()
    log.info("ocr: done, skipped %d/%d frames", skipped, len(shots))
