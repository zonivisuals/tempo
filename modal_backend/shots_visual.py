"""Tier 0: shot detection, keyframes, CLIP visual embeds, clustering.

Mechanical port of `tempo_pipeline_v3.ipynb` cell af283162 — the notebook is the
behavioral reference; this module is the deployable one. Bodies below are
verbatim except the logged deviations. Re-verify against the notebook on any
pipeline change (golden + parity tests guard drift).

Deviations from verbatim:
  - download_youtube_video DROPPED (Modal ingests from storage, not
    YouTube; kept in notebook only);
  - cross-cell names become explicit imports via ._deps;
  - top-level `import os` dropped (the function-level import serves makedirs);
  - `del x; gc.collect(); …` semicolons kept verbatim (ruff E702 exempt file-wide);
  - _need() guards at entries.
"""
# ruff: noqa: E702
import gc

import numpy as np

from . import _deps
from ._deps import _need

try:
    import cv2
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("opencv-python", _err)
    cv2 = None  # type: ignore[no-redef,assignment]

try:
    from scenedetect import open_video, SceneManager, AdaptiveDetector
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("scenedetect", _err)
    open_video = None  # type: ignore[no-redef,assignment]
    SceneManager = None  # type: ignore[no-redef,assignment]
    AdaptiveDetector = None  # type: ignore[no-redef,assignment]

try:
    from transformers import CLIPProcessor, CLIPVisionModelWithProjection
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("transformers", _err)
    CLIPProcessor = None  # type: ignore[no-redef,assignment]
    CLIPVisionModelWithProjection = None  # type: ignore[no-redef,assignment]

try:
    from sklearn.cluster import KMeans
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("scikit-learn", _err)
    KMeans = None  # type: ignore[no-redef,assignment]

try:
    from sklearn.metrics import silhouette_score
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("scikit-learn", _err)
    silhouette_score = None  # type: ignore[no-redef,assignment]

try:
    import torch
except ImportError as _err:  # guarded; failure recorded for _need()
    _deps.note("torch", _err)
    torch = None  # type: ignore[no-redef,assignment]
DEVICE = _deps.device()

def _laplacian_sharpness(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def extract_shots_and_keyframes(video_path, out_dir="."):
    _need(open_video, "scenedetect")
    _need(cv2, "opencv-python")
    import os
    os.makedirs(out_dir, exist_ok=True)
    """
    AdaptiveDetector + 3-candidate Laplacian sharpness.
    frame_bgr retained alongside frame_rgb to avoid re-reading from disk
    in the OCR step.
    """
    video = open_video(video_path)
    sm    = SceneManager()
    sm.add_detector(AdaptiveDetector())
    sm.detect_scenes(video)
    scenes = sm.get_scene_list()

    cap       = cv2.VideoCapture(video_path)
    keyframes = []

    for i, (start, end) in enumerate(scenes):
        dur  = end.get_seconds() - start.get_seconds()
        best_frame, best_score = None, -1.0
        for ratio in (0.25, 0.50, 0.75):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start.get_seconds() + dur * ratio) * 1000)
            ret, frame = cap.read()
            if ret:
                score = _laplacian_sharpness(frame)
                if score > best_score:
                    best_score, best_frame = score, frame

        if best_frame is not None:
            path = os.path.join(out_dir, f"keyframe_{i}.jpg")
            cv2.imwrite(path, best_frame)
            keyframes.append({
                "shot_id":       i,
                "start_time":    start.get_seconds(),
                "end_time":      end.get_seconds(),
                "duration":      dur,
                "keyframe_path": path,
                "frame_rgb":     cv2.cvtColor(best_frame, cv2.COLOR_BGR2RGB),
                "frame_bgr":     best_frame,
            })

    cap.release()
    print(f"Extracted {len(keyframes)} shots.")
    return keyframes


def get_visual_embeddings_and_cluster(keyframes, max_clusters=15, chunk_size=32):
    """
    CLIP visual embeddings + KMeans (k picked by silhouette) + rep flagging.
    """
    _need(torch, "torch")
    _need(CLIPVisionModelWithProjection, "transformers")
    _need(KMeans, "scikit-learn")
    model     = CLIPVisionModelWithProjection.from_pretrained(_deps.CLIP_MODEL).to(DEVICE)
    processor = CLIPProcessor.from_pretrained(_deps.CLIP_MODEL)
    model.eval()

    all_embs = []
    images   = [kf["frame_rgb"] for kf in keyframes]
    for start in range(0, len(images), chunk_size):
        chunk  = images[start:start + chunk_size]
        inputs = processor(images=chunk, return_tensors="pt", padding=True).to(DEVICE)
        with torch.no_grad():
            embs = model(**inputs).image_embeds
        embs = embs / embs.norm(p=2, dim=-1, keepdim=True)
        all_embs.append(embs.cpu().numpy())

    emb_matrix = np.vstack(all_embs).astype(np.float32)
    for i, kf in enumerate(keyframes):
        kf["visual_embedding"] = emb_matrix[i]

    del model, processor; gc.collect(); torch.cuda.empty_cache()
    print("Visual embeddings done.")

    n = len(keyframes)
    if n < 4:
        for kf in keyframes:
            kf["cluster_id"]    = 0
            kf["is_cluster_rep"] = True
        return

    max_k     = min(max_clusters, n // 3)
    best_k, best_sil = 2, -1.0
    for k in range(2, max_k + 1):
        km  = KMeans(n_clusters=k, random_state=42, n_init=10)
        lbl = km.fit_predict(emb_matrix)
        sil = silhouette_score(emb_matrix, lbl, sample_size=min(1000, n))
        if sil > best_sil:
            best_k, best_sil = k, sil

    kmeans   = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(emb_matrix)
    for i, kf in enumerate(keyframes):
        kf["cluster_id"] = int(clusters[i])

    for c in range(best_k):
        idx   = np.where(clusters == c)[0]
        dists = np.linalg.norm(emb_matrix[idx] - kmeans.cluster_centers_[c], axis=1)
        top_n = 2 if len(idx) >= 3 else 1
        for rel in np.argsort(dists)[:top_n]:
            keyframes[idx[rel]]["is_cluster_rep"] = True

    print(f"Clustered k={best_k} (sil={best_sil:.3f}).")