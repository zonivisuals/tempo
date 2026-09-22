"""Modal deployment wiring (ADR-0004). Imported ONLY on deploy hosts.

Deploy: `modal deploy modal_backend/modal_app.py` (needs `pip install modal`
plus a Modal token — never in git). Verify decorator/option names against
https://modal.com/docs/guide before first deploy; the interface contract
(docs/api.md backend subset) is what CI pins, not these options.

Layout on Modal:
  Volume "tempo-artifacts"  mounted at /artifacts  (shots.json, npz, thumbs)
  Volume "tempo-checkpoints" mounted at /checkpoints (per-stage resume)
  Secret "tempo-secrets"    provides BACKEND_TOKEN (the entire auth model)
  modal_api (below)         ASGI app: /health /index /jobs /search /thumb
  run_stage (below)         GPU function executing pipeline.run_all
"""

APP_NAME = "tempo"
ARTIFACTS_MOUNT = "/artifacts"
CHECKPOINTS_MOUNT = "/checkpoints"

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


def build():
    """Construct the Modal App. Called by `modal deploy`, never by tests."""
    import modal

    app = modal.App(APP_NAME)
    image = modal.Image.debian_slim(python_version="3.11").pip_install(*PINNED_DEPS)
    artifacts = modal.Volume.from_name("tempo-artifacts", create_if_missing=True)
    checkpoints = modal.Volume.from_name("tempo-checkpoints", create_if_missing=True)
    secrets = modal.Secret.from_name("tempo-secrets")

    @app.function(
        image=image,
        gpu="T4",
        volumes={ARTIFACTS_MOUNT: artifacts, CHECKPOINTS_MOUNT: checkpoints},
        secrets=[secrets],
        timeout=3600,
    )
    def run_stage(drive_path: str, progress=None):
        # Executed on the GPU worker. progress() streams done/total per stage
        # back to the caller (index job), which mirrors them into job state.
        # drive_path must already resolve on the worker (P2 wires volume
        # ingress; until then the GPU trial stages files manually) —
        # otherwise pipeline.run_all raises FileNotFoundError naming it.
        from modal_backend import pipeline

        key = drive_path.rsplit("/", 2)[-2] if "/" in drive_path else "job"
        out = f"{ARTIFACTS_MOUNT}/{key}"
        return pipeline.run_all(drive_path, out, progress or (lambda s, d, t: None))

    @app.function(
        image=image,
        volumes={ARTIFACTS_MOUNT: artifacts, CHECKPOINTS_MOUNT: checkpoints},
        secrets=[secrets],
    )
    @modal.asgi_app()
    def api():
        import os

        from modal_backend.modal_api import create_app

        return create_app(
            auth_token=os.environ.get("BACKEND_TOKEN", ""),
            artifacts_root=ARTIFACTS_MOUNT,
            checkpoint_root=CHECKPOINTS_MOUNT,
        )

    return app


# Module level on purpose: `modal deploy` looks for `app`, and importing
# this file anywhere without `modal` installed fails loudly naming it.
app = build()
