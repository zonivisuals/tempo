import tempfile

import modal

from workers.modal_config import app, image, gpu_config, secret
from workers.core.storage import download_file
from workers.core.db import get_connection, update_shot_transcript


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def transcribe(data: dict) -> dict:
    s3_key = data["s3_key"]
    video_id = data["video_id"]
    shots = data["shots"]
    import whisper

    model = whisper.load_model("base")

    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        download_file(s3_key, f.name)
        result = model.transcribe(f.name, word_timestamps=True)

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
        conn.close()

    return {"ok": True}
