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
  Secret "tempo-secrets"     provides BACKEND_TOKEN (the entire auth model)
  api (below)                ASGI app: /health /index /jobs /search/thumb
                             (indexing + query embedding run in-process;
                             the worker calls pipeline.run_all directly)

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
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(*PINNED_DEPS)
    .add_local_dir("modal_backend", remote_path="/root/modal_backend")
)
artifacts = modal.Volume.from_name("tempo-artifacts", create_if_missing=True)
checkpoints = modal.Volume.from_name("tempo-checkpoints", create_if_missing=True)
ingress = modal.Volume.from_name("tempo-ingress", create_if_missing=True)
secrets = modal.Secret.from_name("tempo-secrets")

_gpu = _os.environ.get("TEMPO_MODAL_GPU", "T4") or None


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
