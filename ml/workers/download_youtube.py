import os
import tempfile
import shutil

import modal

from workers.modal_config import app, image, secret
from workers.core.storage import upload_fileobj


@app.function(image=image, secrets=[secret], timeout=1200)
@modal.fastapi_endpoint(method="POST")
def download_youtube(data: dict) -> dict:
    import yt_dlp

    url = data["url"]
    s3_key = data["s3_key"]

    tmpdir = tempfile.mkdtemp()
    try:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        with open(filename, "rb") as f:
            upload_fileobj(s3_key, f)

        return {
            "ok": True,
            "s3_key": s3_key,
            "title": info.get("title"),
            "duration": info.get("duration"),
        }
    except Exception as e:
        return {"ok": False, "s3_key": s3_key, "error": str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
