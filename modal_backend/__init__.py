"""Tempo Modal backend (ADR-0004).

Deployable port of the notebook pipeline stages (cells b25be17b–8241b95a).
Stage modules are mechanical extractions — see each file's header for
provenance and the (logged) deviations. The notebook stays the behavioral
reference; golden + parity tests guard drift.

Layout:
  _deps.py        device probe, model names, _need() tripwire
  singletons.py   CLIP-text + NER singletons (cell b25be17b)
  shots_visual.py Tier 0 shots/keyframes/visual-embed/cluster (cell af283162)
  audio_ocr.py    Tier 1 whisper/OCR/alignment (cell 6fd10aa2)
  ner.py          shared entity extractor (cell cfba7b76)
  enrich.py       Tier 2 BLIP-2/ NER / text-embed (cell 4b9c917c)
  indices.py      FAISS + BM25 build (cell 8241b95a, UMAP excluded)
  scoring.py      pure §3.5 fusion (parity-tested vs service.search)
  pipeline.py     stage orchestration + artifact persistence
  modal_api.py    FastAPI contract app (no modal import; testable on CPU)
  modal_app.py    Modal deploy wiring (imported only with `modal` installed)
"""
