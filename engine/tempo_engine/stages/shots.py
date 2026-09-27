"""Tier 0 — shots and keyframes.

Port of notebook cell f98b5375 (`_sharpness`, `_resize_max`, `detect_shots`).

Deviations from the notebook:
  - scene detection runs in `shot_scan_step_s` chunks (`detect_scenes(duration=)`
    continues from the current position — verified against a single pass on a
    synthetic clip) so the stage reports frames scanned;
  - `download_youtube` dropped (the engine ingests uploads only);
  - frame ratios, max side and JPEG quality come from config.
"""

import math

from ..cache import StageCache
from ..config import settings
from . import Progress

FRAMES_DIR = "frames"


def _sharpness(frame) -> float:  # type: ignore[no-untyped-def]
    import cv2

    return cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


def _resize_max(frame, max_side: int):  # type: ignore[no-untyped-def]
    import cv2

    h, w = frame.shape[:2]
    s = max_side / max(h, w)
    return cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else frame


def split_spans(scenes: list[tuple[float, float]], max_shot_sec: float) -> list[tuple[float, float, int]]:
    """Long cuts split into equal sub-shots of at most max_shot_sec, tagged with their scene id."""
    spans = []
    for scene_id, (s, e) in enumerate(scenes):
        parts = max(1, math.ceil((e - s) / max_shot_sec - 1e-6))
        step = (e - s) / parts
        spans += [(s + k * step, s + (k + 1) * step, scene_id) for k in range(parts)]
    return spans


def detect_shots(video_path: str, cache: StageCache, progress: Progress) -> dict:
    """AdaptiveDetector cuts, long cuts split into <= max_shot_sec sub-shots.
    3 frames per shot (20/50/80 %) are saved; the sharpest is the display keyframe."""
    import cv2
    from scenedetect import AdaptiveDetector, SceneManager, open_video

    video = open_video(video_path)
    fps = float(video.frame_rate)
    try:
        duration = video.duration.get_seconds()
        total_frames = int(video.duration.get_frames())
    except Exception:
        cap0 = cv2.VideoCapture(video_path)
        total_frames = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / max(cap0.get(cv2.CAP_PROP_FPS), 1)
        cap0.release()

    sm = SceneManager()
    sm.add_detector(AdaptiveDetector())
    scanned = 0
    progress(0, total_frames)
    while True:
        n = sm.detect_scenes(video, duration=settings.shot_scan_step_s)
        if n <= 0:
            break
        scanned += n
        progress(min(scanned, total_frames), total_frames)
    scenes = [(s.get_seconds(), e.get_seconds()) for s, e in sm.get_scene_list()] or [(0.0, duration)]
    spans = split_spans(scenes, settings.max_shot_sec)

    (cache.dir / FRAMES_DIR).mkdir(exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    shots = []
    for s, e, scene_id in spans:
        sid = len(shots)
        paths, best, best_score = [], None, -1.0
        for k, r in enumerate(settings.frame_ratios):
            cap.set(cv2.CAP_PROP_POS_MSEC, (s + (e - s) * r) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            frame = _resize_max(frame, settings.frame_max_side)
            rel = f"{FRAMES_DIR}/shot{sid:05d}_{k}.jpg"
            cv2.imwrite(cache.abs(rel), frame, [cv2.IMWRITE_JPEG_QUALITY, settings.frame_jpeg_quality])
            paths.append(rel)
            score = _sharpness(frame)
            if score > best_score:
                best_score, best = score, rel
        if paths:
            shots.append(dict(shot_id=sid, scene_id=scene_id, start_time=float(s), end_time=float(e),
                              duration=float(e - s), frame_paths=paths, keyframe_path=best))
    cap.release()
    return {"fps": fps, "duration": float(duration), "shots": shots, "n_scenes": len(scenes)}
