"""Stage 1 `shots`: scene detection + keyframes (AGENTS.md §3.2).

OpenCV + PySceneDetect `AdaptiveDetector` (rolling-average HSV detector,
robust to fast camera motion):
https://github.com/Breakthrough/PySceneDetect — `SceneManager.add_detector`,
`detect_scenes`, `get_scene_list`.

Per shot, 3 candidates @0.25/0.50/0.75 are scored by Laplacian variance and
the sharpest is saved as `thumbs/shot_<id>.jpg` (quality 85).
"""

import logging
from pathlib import Path

log = logging.getLogger("tempo.shots")


def detect_shots(video_path: str, thumbs_dir: str, progress=None) -> tuple[list[dict], float, float]:  # type: ignore[no-untyped-def]
    import cv2
    import numpy as np
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import AdaptiveDetector

    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(AdaptiveDetector())
    manager.detect_scenes(video)
    scenes = manager.get_scene_list()
    log.info("detected %d scenes in %s", len(scenes), video_path)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration_s = (frame_count / fps) if fps else 0.0

    thumbs = Path(thumbs_dir)
    thumbs.mkdir(parents=True, exist_ok=True)

    shots: list[dict] = []
    total = len(scenes) if scenes else 1
    if not scenes:  # single-shot fallback (e.g. very short clip)
        scenes = [(None, None)]

    for i, scene in enumerate(scenes):
        if scene[0] is None:
            start_s, end_s = 0.0, duration_s
        else:
            start_s = scene[0].get_seconds()
            end_s = scene[1].get_seconds()
        keyframe = _sharpest_frame(cap, fps, start_s, end_s)
        out = thumbs / f"shot_{i}.jpg"
        cv2.imwrite(str(out), keyframe, [cv2.IMWRITE_JPEG_QUALITY, 85])
        shots.append(
            {"shot_id": i, "start_s": start_s, "end_s": end_s, "keyframe": str(out)}
        )
        if progress is not None:
            progress("shots", i + 1, total)

    cap.release()
    return shots, fps, duration_s


def _sharpest_frame(cap, fps: float, start_s: float, end_s: float):  # type: ignore[no-untyped-def]
    """Sharpest of 3 candidates by Laplacian variance (research artifact)."""
    import cv2
    import numpy as np

    mid = (start_s + end_s) / 2
    span = max(end_s - start_s, 1.0 / max(fps, 1.0))
    best = None
    best_score = -1.0
    for frac in (0.25, 0.50, 0.75):
        t = start_s + span * frac if span > 0 else mid
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        score = cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        if score > best_score:
            best_score, best = score, frame
    if best is None:  # unreadable shot — black 64px placeholder, never a crash
        best = np.zeros((64, 64, 3), dtype=np.uint8)
    return best
