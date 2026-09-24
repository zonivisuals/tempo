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

# Import-failure reasons, keyed by pip name. Guarded `except ImportError`
# blocks record here so _need() can name the ROOT cause (e.g. a missing
# system .so that breaks an otherwise-installed package) instead of just
# the missing Python name. Never logged wholesale (may contain paths).
_why: dict[str, str] = {}


def note(pip_name: str, exc: BaseException) -> None:
    _why[pip_name] = str(exc)[:200]


def purge_hf_file(repo_id: str, filename: str) -> list:
    """Delete cached copies of filename for an HF repo (corrupt-download
    self-heal). Layout: $HF_HUB_CACHE/models--<org>--<name>/snapshots/*/.
    Returns removed paths. Never raises (a purge that fails must not mask
    the original error); empty result means nothing was cached to purge."""
    import os
    from pathlib import Path as _Path

    root = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface")
    base = _Path(root) / ("models--" + repo_id.replace("/", "--")) / "snapshots"
    removed = []
    if not base.is_dir():
        return removed
    for path in sorted(base.rglob(filename)):
        try:
            path.unlink()
            removed.append(str(path))
        except OSError:
            pass
    return removed


def _need(obj: object, pip_name: str) -> None:
    """Tripwire for guarded heavy imports. Raises before the first cryptic
    AttributeError so CPU/test hosts learn exactly what to install (or that
    the stage only runs on a GPU image)."""
    if obj is None:
        reason = _why.get(pip_name, "")
        hint = f" (import failed: {reason})" if reason else ""
        raise ImportError(
            f"modal stage needs {pip_name} (GPU image only): "
            f"pip install {pip_name}{hint}"
        )
