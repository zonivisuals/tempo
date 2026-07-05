import tempfile

import modal
from PIL import Image

from workers.modal_config import app, image, gpu_config, secret
from workers.core.storage import download_file
from workers.core.embeddings import upsert_visual


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def embed_visual(data: dict) -> dict:
    s3_key = data["s3_key"]
    video_id = data["video_id"]
    shots = data["shots"]
    import torch
    from transformers import CLIPProcessor, CLIPModel

    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    for shot in shots:
        thumbnail_key = shot["thumbnailKey"]
        if not thumbnail_key:
            continue

        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            download_file(thumbnail_key, f.name)
            image = Image.open(f.name).convert("RGB")
            inputs = processor(images=image, return_tensors="pt").to(device)

            with torch.no_grad():
                embedding = model.get_image_features(**inputs)
                vector = embedding.cpu().numpy().flatten().tolist()

        upsert_visual(shot["id"], vector, {"videoId": video_id, "shotIndex": shot["shotIndex"]})

    return {"ok": True}
