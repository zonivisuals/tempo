# 0009 — v4 pipeline and z-score fusion

**Status:** accepted. **Date:** 2026-09-27. **Supersedes:** the v3 pipeline
(`tempo_pipeline_v3.ipynb`), §3.5 max-fusion, D3, and D4. D5 and K2 are
updated; K1 is resolved.

## Context

v3 had these problems on real footage:
- The visual key lost every `max()` against text keys (K1).
- Dialogue vectors came from 0–2 words embedded with CLIP's text encoder
  (`"do"` → cos 0.73).
- BLIP-2 needed ~15 GB, and silhouette picked 14 clusters for 179 shots.
- BM25 kept punctuation, and translation zipped misaligned segment lists.

`tempo_pipeline_v4.ipynb` (local reference, gitignored like v3) fixes these,
builds a cached index, and returns structured results shaped for the panel.

## Decision

- **Behavioral reference:** `tempo_pipeline_v4.ipynb`. v3 is dropped.
  `engine/` ports it with a provenance header per module (source notebook
  cell and logged deviations).
- **Keys:**
  - **visual:** SigLIP 2, as the L2-normalized mean of 3 frames per shot.
  - **dialogue:** bge-base-en-v1.5 over a ±3 s English window. Shots with
    fewer than 3 words have no vector (`D_mask`).
  - **caption:** Florence-2 `<DETAILED_CAPTION>` on k = caption-budget
    cluster medoids. Each shot takes its nearest rep's caption, and
    `caption_conf` down-weights propagated captions.
  - Long takes split at `max_shot_sec` (8 s).
- **Speech:** faster-whisper with Silero VAD and a hallucination filter.
  English translation is aligned by timestamp, never by list index.
- **OCR:** EasyOCR on the full frame, with an edge-fraction prefilter, a
  confidence filter, and a language-matched reader.
- **NER (D5 updated):** `aggregation_strategy="first"` plus span-based
  rebuild (`'A'+'##kita'` → `Akita`), video-level canonical casing, and
  typo-tolerant query resolution (OSA distance ≤ 1 or 2 against the
  video's vocabulary). One extractor serves both query and shots.
- **BM25:** regex tokenizer with stopwords and CJK bigrams. Query tokens
  are extended with the resolved entities.
- **Fusion (K1 resolved):** per-key positive z-score, clipped at 3 and
  scaled to [0, 1], then a weighted sum:
  `visual .35, dialogue .25, caption .15 (× caption_conf), bm25 .15,
  entity .10, anchor .05`.
  - Weights are config and excluded from the index signature, so retuning
    them never reindexes.
  - Contributions sum exactly to the score.
  - Results scoring ≤ 0 are dropped, and one result is kept per scene.
- **FAISS querying:**
  - Each dense key has an `IndexFlatIP` over the searched corpus
    (`IndexIDMap` over `D_mask` rows for dialogue). FAISS top-K per key,
    plus BM25/entity hits, forms the candidate set, and `I[]` is always
    mapped back to shot rows.
  - Z-scores stay exact without a full scan. They use the corpus mean and
    Gram matrix: μ = q·m and σ² = qᵀGq/n − μ².
  - With n ≤ `faiss_candidates` the result equals the notebook's
    exhaustive search (parity-tested). Beyond that, the candidate union is
    the documented approximation.
  - Scale path: swap the flat index for HNSW behind config, then
    revalidate against the goldens.
- **Signature:** the index is valid while
  `meta.signature == config_signature()`. That covers pipeline version,
  models, and indexing parameters (weights excluded). A mismatch reads as
  `stale` and rebuilds through the stage cache.

## Consequences

- The search payload is v2: `contributions` has six components,
  `raw_cos.dialogue` is nullable, `winning_key` is gone, and `entities`
  moves to top level. Scoring moves to the engine, and the goldens move
  with it.
- K2 (inherited captions) persists but is weaker: `caption_conf` scales a
  borrowed caption by its visual similarity to the rep.
- Across several footages, z-scores and BM25 IDF are computed over the
  searched union, so a single footage matches the notebook exactly.
