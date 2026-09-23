# 0004 — Modal-hosted pipeline behind a backend seam, Colab tunnel deleted

**Status:** accepted. **Date:** 2026-09-22. **Supersedes:** ADR-0002 (Colab remote
pipeline) for the serving path. ADR-0003's `tempo/<key>/<basename>` key contract
is kept; its Drive transport is replaced in P2 (storage providers).

## Context

The Colab + ngrok setup proved the split (GPU elsewhere, thin local service)
but cannot be sold or operated: per-session URLs pasted by hand, free-tier
preemption/TOS, bearer tokens in env/localStorage, and — worst — a service
endpoint (`POST /colab-url`) accepting an arbitrary backend URL from panel
input, which makes the local service an open proxy. Production needs a real
GPU host with stable addresses, server-side secrets, and a seam that lets the
backend change without touching panel, scoring, or contracts.

## Decision

- **Backend seam:** `service/tempo_service/backends/` owns one interface
  (`base.py`: health/submit_index/job_status/search/thumb_bytes, `BackendError`
  with `BACKEND_UNREACHABLE/ASLEEP/TIMEOUT`). `HttpBackend` (stdlib urllib)
  speaks the docs/api.md contract to any HTTPS backend. `get_provider()`
  returns None for `backend="local"` (in-process indexer, kept for dev).
  Error codes renamed `COLAB_*` → `BACKEND_*` in the same mechanical pass.
- **Modal serves it:** `modal_backend/` is the deployable port — notebook
  cells b25be17b–8241b95a extracted mechanically (provenance + deviation log
  per file), `modal_api.py` implements the backend contract (job lifecycle,
  checkpoints, §3.5 scoring parity-tested, thumb serving, bearer auth),
  `modal_app.py` wires Modal (App, T4 image with pinned deps, Volumes for
  artifacts/checkpoints, Secret for the token, ASGI mount). Verify decorator
  names against https://modal.com/docs/guide at first deploy.
- **Deleted:** `service/tempo_service/colab.py`, `POST /colab-url`,
  `TEMPO_COLAB_*` config, panel Colab-URL box + `tempo_colab_url` storage.
  Backend address/token are server config (`TEMPO_BACKEND*`), never user input.
- **Kept working:** the gitignored `colab/tempo_shim.py` still speaks the
  contract, so `backend="http"` pointed at a tunnel stays a valid dev setup —
  it is simply no longer special-cased anywhere.
- **Durable job envelopes:** every job transition persists to
  `checkpoints/_jobs/<id>.json`, so any container serves status for any job
  (concurrent panel polling across containers never false-404s). The proxy
  additionally rides out transient poll misses (5×1s) before failing a job.
- **Kept:** scoring contract (§3.5) byte-identical (parity test), job states
  (renamed `queued-for-colab` → `queued-for-backend`), retry flows, thumb
  fallback + cache, source_path backfill, loader fallback, Drive-shaped
  storage key (tenant prefix lands with auth in P1).

## Consequences

- Panel shows `backend ok/gpu/local only`; no per-session setup. Local dev
  stays fully offline (`backend="local"`).
- GPU stage bodies ship unexecuted until the GPU trial validates them
  (progress/checkpoint/artifact paths are CPU-tested with fakes; torch paths
  raise named ImportErrors off-GPU by construction).
- Durable multi-container job state needs Postgres (P1); until then the
  gateway's poll/retry semantics cover restarts.

## Revisit when

A second backend (Vast.ai spillover, self-hosted) is needed — implement
`BackendProvider`, no panel changes. Or Modal pricing/terms break the model —
the seam is the whole point.
