"""Shared runtime facts for the extracted stages (ADR-0004).

The notebook ran all cells in one GPU process, so names like DEVICE and the
model ids were globals. Real modules can't assume that: this module owns the
device probe, the model-name defaults (env-overridable), and the `_need()`
tripwire that turns "module is None on a CPU/test host" into an actionable
error naming the pip package.
"""

import os


def device() -> str:
    """Same rule as the notebook: cuda when torch sees it, else cpu."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


CLIP_MODEL = os.environ.get("TEMPO_CLIP_MODEL", "openai/clip-vit-large-patch14")
BLIP2_MODEL_NAME = os.environ.get(
    "TEMPO_BLIP2_MODEL", "Salesforce/blip2-opt-2.7b"
)
NER_MODEL_NAME = os.environ.get("TEMPO_NER_MODEL", "dslim/bert-base-NER")


def _need(obj: object, pip_name: str) -> None:
    """Tripwire for guarded heavy imports. Raises before the first cryptic
    AttributeError so CPU/test hosts learn exactly what to install (or that
    the stage only runs on a GPU image)."""
    if obj is None:
        raise ImportError(
            f"modal stage needs {pip_name} (GPU image only): "
            f"pip install {pip_name}"
        )
