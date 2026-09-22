"""Model singletons (shared CLIP-text + NER), one resident at a time.

Mechanical port of `tempo_pipeline_v3.ipynb` cell b25be17b — the notebook is the
behavioral reference; this module is the deployable one. Bodies below are
verbatim except the logged deviations. Re-verify against the notebook on any
pipeline change (golden + parity tests guard drift).

Deviations from verbatim:
  - cross-cell names (DEVICE, CLIP_MODEL, pipeline) become explicit
    imports via ._deps (notebook relied on shared cell globals);
  - model names read from env with notebook defaults (configurability);
  - _need() guards at entries (CPU/test hosts get a named error).
"""
from . import _deps
from ._deps import _need

try:
    from transformers import CLIPProcessor, CLIPTextModelWithProjection, pipeline
except ImportError:  # CPU/test host: guarded, _need() explains at call
    CLIPProcessor = None  # type: ignore[no-redef,assignment]
    CLIPTextModelWithProjection = None  # type: ignore[no-redef,assignment]
    pipeline = None  # type: ignore[no-redef,assignment]
DEVICE = _deps.device()

_CLIP_TEXT_MODEL = None
_CLIP_PROCESSOR = None
_NER_PIPELINE = None

def _get_clip_text_model():
    """Singleton — load once, reuse across all search calls and _embed_texts()."""
    global _CLIP_TEXT_MODEL, _CLIP_PROCESSOR
    if _CLIP_TEXT_MODEL is None:
        _CLIP_TEXT_MODEL = CLIPTextModelWithProjection.from_pretrained(_deps.CLIP_MODEL).to(DEVICE)
        _CLIP_PROCESSOR  = CLIPProcessor.from_pretrained(_deps.CLIP_MODEL)
        _CLIP_TEXT_MODEL.eval()
        print("CLIP text model loaded (cached).")
    return _CLIP_TEXT_MODEL, _CLIP_PROCESSOR


def _get_ner_pipeline():
    """Singleton raw NER pipeline (dslim/bert-base-NER)."""
    _need(CLIPTextModelWithProjection, "transformers")
    global _NER_PIPELINE
    if _NER_PIPELINE is None:
        _NER_PIPELINE = pipeline(
            "ner",
            model=_deps.NER_MODEL_NAME,
            aggregation_strategy="simple",
            device=0 if DEVICE == "cuda" else -1,
        )
        print("NER loaded (cached).")
    return _NER_PIPELINE
    _need(pipeline, "transformers")