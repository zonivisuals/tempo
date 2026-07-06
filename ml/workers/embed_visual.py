import tempfile

import modal
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel

from workers.modal_config import app, image, gpu_config, secret
from workers.core.storage import download_file
from workers.core.embeddings import upsert_visual

_clip_model = None
_clip_processor = None
_clip_device = None


def _get_clip():
    global _clip_model, _clip_processor, _clip_device
    if _clip_model is None:
        _clip_device = "cuda" if torch.cuda.is_available() else "cpu"
        _clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(_clip_device)
        _clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    return _clip_model, _clip_processor, _clip_device


@app.function(image=image, gpu=gpu_config, secrets=[secret], timeout=900)
@modal.fastapi_endpoint(method="POST")
def embed_visual(data: dict) -> dict:
    s3_key = data["s3_key"]
    video_id = data["video_id"]
    shots = data["shots"]
    model, processor, device = _get_clip()

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
