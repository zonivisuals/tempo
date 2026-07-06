import tempfile

import modal
import whisper

from workers.modal_config import app, image, gpu_config, secret
from workers.core.storage import download_file
from workers.core.db import get_connection, put_connection, update_shot_transcript

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model("base")
    return _whisper_model


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def transcribe(data: dict) -> dict:
    s3_key = data["s3_key"]
    video_id = data["video_id"]
    shots = data["shots"]

    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        download_file(s3_key, f.name)
        result = _get_whisper_model().transcribe(f.name)

    conn = get_connection()
    try:
        segments = result.get("segments", [])

        for shot in shots:
            shot_start = shot["startTime"]
            shot_end = shot["endTime"]
            shot_words = [
                s for s in segments
                if s["start"] < shot_end and s["end"] > shot_start
            ]
            transcript = " ".join(
                s["text"].strip() for s in shot_words
            )
            update_shot_transcript(conn, shot["id"], transcript)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    return {"ok": True}
