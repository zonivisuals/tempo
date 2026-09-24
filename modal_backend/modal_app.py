"""Modal deployment wiring (ADR-0004).

Deploy: `modal deploy modal_backend/modal_app.py` (needs `pip install modal`
plus a Modal token — never in git). Verify decorator/option names against
https://modal.com/docs/guide before first deploy; the interface contract
(docs/api.md backend subset) is what CI pins, not these options.

Everything Modal-related lives at module scope on purpose: Modal only
imports functions defined in global scope (nested defs fail deploy with
LocalFunctionError), and `modal deploy` looks for the module-level `app`.
Importing this file without `modal` installed fails loudly naming it.

Layout on Modal:
  Volume "tempo-artifacts"   mounted at /artifacts   (shots.json, npz, thumbs)
  Volume "tempo-checkpoints" mounted at /checkpoints (per-stage resume)
  Volume "tempo-ingress"     mounted at /ingress     (raw footage staging:
                             `modal volume put tempo-ingress <file>
                              tempo/<key>/<basename>`; B2 presigned uploads
                             replace this copy step in P2-full)
  Volume "tempo-models"      mounted at /root/.cache/huggingface (verified
                             model cache — see seed.py; runtimes resolve it
                             with zero code changes via HF defaults)
  Secret "tempo-secrets"     provides BACKEND_TOKEN (the entire auth model)
  api (below)                ASGI app: /health /index /jobs /search/thumb
                             (indexing + query embedding run in-process;
                             the worker calls pipeline.run_all directly)
  seed_cache (below)         one-off CPU seeder: `modal run ...::seed_cache`

GPU selection (Modal gates ALL GPUs behind a payment method on file):
  TEMPO_MODAL_GPU=T4 (default) — full trial, needs a card on the account.
  TEMPO_MODAL_GPU="" (empty)   — CPU-only contract smoke, runs on the
                             no-card $5/mo credits. Proves auth, job
                             lifecycle, checkpoints, scoring, thumbs;
                             model stages will 503/error without CUDA.
                             Read at deploy time on the deploy machine.
"""

import modal
import os as _os

APP_NAME = "tempo"
ARTIFACTS_MOUNT = "/artifacts"
CHECKPOINTS_MOUNT = "/checkpoints"
INGRESS_MOUNT = "/ingress"
# Default HF cache path (huggingface_hub + transformers + faster-whisper all
# resolve here when HF_HUB_CACHE is unset). Mounting the models Volume here
# makes the seeded cache visible with zero code changes anywhere.
CACHE_MOUNT = "/root/.cache/huggingface"


# Pinned to service/pyproject.toml versions where the stacks overlap, so the
# deployed pipeline and the golden-tested service share model behavior.
PINNED_DEPS = [
    "fastapi==0.115.6",
    "pydantic==2.9.2",
    "numpy==1.26.4",
    "pillow==10.4.0",
    "opencv-python==4.10.0.84",
    "scenedetect==0.6.4",
    "torch==2.4.1",
    "transformers==4.44.2",
    "accelerate==0.34.2",
    "faster-whisper==1.0.3",
    "easyocr==1.7.2",
    "scikit-learn==1.5.2",
    "faiss-cpu==1.8.0",
    "rank-bm25==0.2.2",
]

app = modal.App(APP_NAME)
# `modal deploy <file>` uploads only that file; the modal_backend package
# (api, pipeline, stages, scoring) ships as an image layer so the
# `from modal_backend...` imports resolve on the worker.
# debian-slim omits shared libs the pipeline needs at import: libGL for
# opencv-python (cv2/scenedetect fail without it) and ffmpeg for audio
# extraction. Without these, stages die with bare ImportErrors that the
# _why recorder then surfaces verbatim in the job payload.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install(*PINNED_DEPS)
    # Code last: redeploys after a stage edit reuse the cached apt+pip layers.
    .add_local_dir("modal_backend", remote_path="/root/modal_backend")
)
artifacts = modal.Volume.from_name("tempo-artifacts", create_if_missing=True)
checkpoints = modal.Volume.from_name("tempo-checkpoints", create_if_missing=True)
ingress = modal.Volume.from_name("tempo-ingress", create_if_missing=True)
models = modal.Volume.from_name("tempo-models", create_if_missing=True)
secrets = modal.Secret.from_name("tempo-secrets")

# CPU by default (no-card safe): set TEMPO_MODAL_GPU=T4 at deploy time to
# opt into GPU explicitly. Never the reverse — a default GPU silently burns
# paid compute on every deploy.
_gpu = _os.environ.get("TEMPO_MODAL_GPU") or None


@app.function(
    image=image,
    gpu=_gpu,
    # torch + transformers import ~1GB RSS; Modal's default container memory
    # OOM-kills the import loop (requests hang instead of answering). 8GB
    # covers import + single-shot CPU inference headroom for the trial.
    memory=8192,
    volumes={
        ARTIFACTS_MOUNT: artifacts,
        CHECKPOINTS_MOUNT: checkpoints,
        INGRESS_MOUNT: ingress,
        CACHE_MOUNT: models,
    },
    secrets=[secrets],
    timeout=3600,
)
@modal.asgi_app()
def api():
    import os

    from modal_backend.modal_api import create_app, ingress_resolver

    return create_app(
        auth_token=os.environ.get("BACKEND_TOKEN", ""),
        artifacts_root=ARTIFACTS_MOUNT,
        checkpoint_root=CHECKPOINTS_MOUNT,
        resolve_source=ingress_resolver(INGRESS_MOUNT),
    )


@app.function(
    image=image,
    volumes={CACHE_MOUNT: models},
    secrets=[secrets],
    timeout=7200,
)
def seed_cache():
    """Populate the shared model cache (CPU-only, pure download + verify).

    Run once per model revision: `modal run modal_backend/modal_app.py::seed_cache`.
    Seeding is idempotent (verified files are skipped by the hub client);
    size mismatches raise SeedError LOUDLY instead of poisoning runs.
    """
    from modal_backend import seed

    return seed.seed_all()
