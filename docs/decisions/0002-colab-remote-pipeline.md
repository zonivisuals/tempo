# 0002 — Colab-hosted pipeline, local service as proxy

**Status:** accepted. **Date:** 2026-09-22. **Supersedes:** D8 assumption of local-GPU indexing (local path kept as documented alternative, not built).

## Context

The 9-stage pipeline (CLIP-L, BLIP-2 2.7B, Whisper large-v3, EasyOCR, BERT-NER)
needs GPU RAM the target machines don't have. The research notebook
(`tempo_pipeline` v3 code) already implements all 9 stages correctly on Colab
free-tier GPUs. Duplicating it locally per machine is cost without benefit for MVP.

## Decision

- **Colab (free tier)** runs the pipeline: the notebook functions verbatim, plus a
  thin FastAPI shim (`colab/tempo_shim.py`): `POST /index {drive_path}`,
  `GET /jobs/{id}` (9 stages, real progress), `GET /search`, `GET /thumb`,
  `GET /health` (reports GPU/CPU). Exposed via ngrok + bearer token (both from
  Colab Secrets). Per-stage checkpoints go to Drive (`tempo/checkpoints/<key>/`)
  so free-tier preemption resumes instead of restarting.
- **Local service** keeps: registry (+ `drive_path` link, §3.3), single-worker
  **proxy** queue (handoff → poll 500 ms → thumb/sync on completion), search
  proxy, local thumb cache, Colab reachability in `/health`.
- **Scoring contract (§3.5) is untouched.** Colab runs the notebook formula, which
  *is* the reference; local `search.py` stays as the golden-tested contract +
  future self-hosted path. Any formula change still needs golden + §3.5 + log.
- **Local `indexer/` stages are deleted in P9** (§8: no dead code). The notebook
  remains the pipeline reference.

## Consequences

- F2 `<300 ms` becomes a tunneled budget (thumbs local-instant, results on
  Colab time, timeout + inline error). Offline search is impossible; the panel
  shows Colab asleep/unreachable states instead of spinners.
- ngrok URL churn per session → panel Colab-URL setting (persisted locally).
- Public tunnel URL + bearer token is the entire auth model (documented in §3.4).

## Revisit when

A local GPU baseline exists (then: revive `indexer/` behind a config flag,
golden-parity against Colab) or Colab terms break the tunnel model (then: Modal
or self-hosted worker — see legacy `vid-ind-api` dispatch notes, do not copy
its Qdrant/BullMQ stack).
