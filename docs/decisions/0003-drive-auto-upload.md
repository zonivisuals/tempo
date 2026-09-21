# 0003 — Drive auto-upload on AE import

**Status:** accepted. **Date:** 2026-09-22.

## Context

Colab reads footage from Drive, but the editor's files live on local disk next
to AE. Any manual copy/upload step breaks F1 ("import → indexing with zero
clicks"). The panel cannot touch the filesystem (no Node.js context), but the
local service can — so the service owns the upload.

## Decision

- On `POST /sync`, unknown fingerprints enter **`uploading`** state. A
  single-worker Drive uploader (`service/tempo_service/drive.py`, resumable
  uploads via Drive API) pushes bytes to the deterministic name
  **`tempo/<footage_key>/<basename>`** (`footage_key` = existing
  `sha1(local_path)[:10]` — stable across re-imports).
- **Dedupe:** same key + size already on Drive → skip bytes, go straight to indexing.
- **Honest progress:** `uploaded_bytes/total_bytes` polled at 500 ms like any
  stage. Removing the footage from the project cancels the upload.
- **Auth:** one-time Google OAuth consent (`POST /drive-auth` bootstrap);
  token cached outside the repo (config path, never committed). Revoked token →
  job `error` with a re-auth hint, never a silent stall.
- **Handoff:** upload done → Colab `POST /index {drive_path}` automatically.
  Colab asleep at handoff → job waits in **`queued-for-colab`** (retried each
  poll), not failed.

## Consequences

- New footage/job states (`uploading`, `queued-for-colab`); F1 acceptance
  covers the upload leg; `/sync` reports `uploads` alongside `jobs`.
- Extra deps: `google-api-python-client`, `google-auth-oauthlib` (pinned, P9).
- Upload bandwidth (not GPU) becomes the first-leg bottleneck — the trial (P10)
  measures it on a short clip first.
