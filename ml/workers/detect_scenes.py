import tempfile

import modal

from workers.modal_config import app, image, gpu_config, secret
from workers.core.storage import download_file, upload_bytes
from workers.core.db import get_connection, insert_shot


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def detect_scenes(data: dict) -> dict:
    s3_key = data["s3_key"]
    video_id = data["video_id"]
    team_id = data["team_id"]
    threshold = data.get("threshold", 27.0)
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector
    import cv2

    conn = get_connection()
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            download_file(s3_key, f.name)

            video = open_video(f.name)
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            cap = cv2.VideoCapture(f.name)
            fps = cap.get(cv2.CAP_PROP_FPS)

            shots = []
            for i, (start, end) in enumerate(scene_list):
                start_sec = int(start.get_seconds())
                end_sec = int(end.get_seconds())
                mid_frame = int((start.get_seconds() + end.get_seconds()) / 2 * fps)

                thumbnail_key = f"thumbnails/{video_id}/shot_{i}.jpg"
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
                ret, frame = cap.read()
                if ret:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    upload_bytes(thumbnail_key, buf.tobytes())

                shot_id = insert_shot(conn, video_id, i, start_sec, end_sec, thumbnail_key)

                shots.append({
                    "id": shot_id,
                    "shotIndex": i,
                    "startTime": start_sec,
                    "endTime": end_sec,
                    "thumbnailKey": thumbnail_key,
                })

            cap.release()

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"shots": shots}
