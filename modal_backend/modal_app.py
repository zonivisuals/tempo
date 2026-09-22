"""Modal deployment wiring (ADR-0004). Imported ONLY on deploy hosts.

Deploy: `modal deploy modal_backend/modal_app.py` (needs `pip install modal`
plus a Modal token — never in git). Verify decorator/option names against
https://modal.com/docs/guide before first deploy; the interface contract
(docs/api.md backend subset) is what CI pins, not these options.

Layout on Modal:
  Volume "tempo-artifacts"   mounted at /artifacts   (shots.json, npz, thumbs)
  Volume "tempo-checkpoints" mounted at /checkpoints (per-stage resume)
  Volume "tempo-ingress"     mounted at /ingress     (raw footage staging:
                             `modal volume put tempo-ingress <file>
                              tempo/<key>/<basename>`; B2 presigned uploads
                             replace this copy step in P2-full)
  Secret "tempo-secrets"     provides BACKEND_TOKEN (the entire auth model)
  api (below)                GPU ASGI app: /health /index /jobs /search/thumb
                             (indexing + query embedding run in-process on T4;
                             the worker calls pipeline.run_all directly)
"""

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


def build():
    """Construct the Modal App. Called by `modal deploy`, never by tests."""
    import modal

    app = modal.App(APP_NAME)
    image = modal.Image.debian_slim(python_version="3.11").pip_install(*PINNED_DEPS)
    artifacts = modal.Volume.from_name("tempo-artifacts", create_if_missing=True)
    checkpoints = modal.Volume.from_name("tempo-checkpoints", create_if_missing=True)
    ingress = modal.Volume.from_name("tempo-ingress", create_if_missing=True)
    secrets = modal.Secret.from_name("tempo-secrets")

    @app.function(
        image=image,
        gpu="T4",
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

    return app


# Module level on purpose: `modal deploy` looks for `app`, and importing
# this file anywhere without `modal` installed fails loudly naming it.
app = build()
