import tempfile

import modal
import cv2
import insightface
from insightface.app import FaceAnalysis

from workers.modal_config import app, image, gpu_config, secret
from workers.core.storage import download_file
from workers.core.embeddings import upsert_face
from workers.core.db import get_connection, put_connection, set_shot_has_face

_face_app = None


def _get_face_app():
    global _face_app
    if _face_app is None:
        _face_app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        _face_app.prepare(ctx_id=0, det_size=(640, 640))
    return _face_app


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def detect_faces(data: dict) -> dict:
    s3_key = data["s3_key"]
    video_id = data["video_id"]
    shots = data["shots"]
    face_app = _get_face_app()

    conn = get_connection()
    try:
        face_count = 0

        for shot in shots:
            thumbnail_key = shot["thumbnailKey"]
            if not thumbnail_key:
                continue

            with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
                download_file(thumbnail_key, f.name)
                img = cv2.imread(f.name)
                if img is None:
                    continue

                faces = face_app.get(img)

            if faces:
                set_shot_has_face(conn, shot["id"])
                face_count += 1

                face = faces[0]
                vector = face.embedding.tolist()
                upsert_face(shot["id"], vector, {"videoId": video_id, "shotIndex": shot["shotIndex"]})

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    return {"faceCount": face_count}
