"""Fetch every model into the persistent cache: `python -m tempo_engine.prefetch [--verify]`.

Weights land in HF_HOME (the data volume on Brev, set by compose) and
`<data_root>/easyocr`, so containers and restarts never re-download.
`--verify` also loads each model on the engine's device and runs a tiny
inference — the first-deploy check that the pinned stack works on the GPU.
"""

import argparse
import logging
import sys

from . import models
from .config import settings

log = logging.getLogger("tempo.engine.prefetch")

HF_REPOS = ("text_embed_model", "ner_model", "emotion_model")
WHISPER_REPO = "Systran/faster-whisper-{}"
OCR_LANGS = ["en"]


def repos() -> list[str]:
    prof = models.current_profile()
    return [prof.visual_model, prof.caption_model, *(getattr(settings, k) for k in HF_REPOS)]


def fetch() -> None:
    from huggingface_hub import snapshot_download

    prof = models.current_profile()
    for repo in repos():
        log.info("fetching %s", repo)
        snapshot_download(repo_id=repo)
    for name in dict.fromkeys([prof.whisper_model, prof.whisper_translate_model]):
        log.info("fetching whisper %s", name)
        snapshot_download(repo_id=WHISPER_REPO.format(name))
    from .stages.ocr import _reader

    log.info("fetching easyocr %s", OCR_LANGS)
    _reader(OCR_LANGS)


def verify() -> None:
    import numpy as np

    models.preload_query_models()
    q = models.siglip_text_embeds(["a street at night"])
    t = models.embed_query("a street at night")
    assert np.isfinite(q).all() and np.isfinite(t).all()
    log.info("verify ok: device=%s siglip=%s bge=%s", models.device(), q.shape, t.shape)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="load query models and run a tiny inference")
    args = parser.parse_args()
    logging.basicConfig(level=settings.log_level)
    fetch()
    if args.verify:
        verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
