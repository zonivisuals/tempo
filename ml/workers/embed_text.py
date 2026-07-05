import modal

from workers.modal_config import app, image, gpu_config, secret
from workers.core.db import get_connection
from workers.core.embeddings import upsert_text


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def embed_text(data: dict) -> dict:
    video_id = data["video_id"]
    shots = data["shots"]
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    conn = get_connection()
    try:
        for shot in shots:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT transcript FROM shots WHERE id = %s",
                    (shot["id"],),
                )
                row = cur.fetchone()

            if not row or not row[0]:
                continue

            transcript = row[0]
            vector = model.encode(transcript).tolist()
            upsert_text(shot["id"], vector, {"videoId": video_id, "shotIndex": shot["shotIndex"]})
    finally:
        conn.close()

    return {"ok": True}
