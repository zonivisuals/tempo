# 0008 — Brev L4 engine, port-forward tunnel, content-addressed cache

**Status:** accepted. **Date:** 2026-09-27. **Supersedes:** ADR-0004 (Modal
backend) and the transport parts of ADR-0003 (Drive key) and ADR-0006
(S3/B2 presigned storage). ADR-0006's retention call (purge raw after
index) is kept.

## Context

The Modal deploy ran CPU-by-default, and three of its promises never held:
- Checkpoints were written but never read back, so nothing resumed.
- S3 uploads landed in a bucket the backend never read.
- Thumbs and `shots.json` were never synced down.

The offline `indexer/` could not import its own config. Separately, v4
(ADR-0009) needs ~8 GB of resident GPU weights, which rules out the target
editor machines.

We want one GPU host with a stable address and persistent disk, no
per-session URLs, and no reindexing of footage the system has already seen.

## Decision

- **Host:** one NVIDIA Brev instance, `tempo-l4-instance`.
  - GPU: L4, 22 GB (docs: GPU types).
  - `/home/ubuntu/workspace` survives stop/start (docs: GPU instances →
    data persistence). It is mounted as the engine's `/data`.
  - The instance is created in the Brev console. Scripts use only CLI
    commands verified in the docs: `exec`, `port-forward`, `start`/`stop`.
- **Engine:** `engine/` (package `tempo_engine`) runs the v4 pipeline and
  search.
  - Docker Compose, with the GPU reservation from the Brev
    custom-containers guide and `restart: unless-stopped`.
  - The API is bound to `127.0.0.1` on the instance, with a bearer token on
    every route except `/v1/health`.
  - Contract: `docs/engine-api.md`.
- **Tunnel:** Brev tunnels require a browser login, and the docs direct
  API clients to `brev port-forward`.
  - The sidecar supervises `brev port-forward <instance> --port L:R` as a
    child process, with backoff restarts and `up|down|off` in `/health`.
  - Instance name and CLI command are config (`TEMPO_BREV_INSTANCE`,
    `TEMPO_BREV_CLI`; `wsl brev` on Windows, per the Brev install docs).
- **Upload:** the sidecar streams footage straight to the engine in
  resumable chunks (`PUT /v1/uploads/{cid}?offset=`) with real byte
  progress.
  - A wrong offset returns `409` with the engine's offset, so drops resume
    instead of restarting.
  - The engine re-derives the content id of the finished file before
    accepting it.
  - No third-party bucket. Raw footage is purged after index
    (`raw_retention=delete`).
- **Content-addressed cache**, three layers:
  1. **Path:** the sidecar registry keeps the `(path, size, mtime_ns)`
     fingerprint and the reopen-safe guards (unchanged).
  2. **Content:** `content_id = sha1(size + first 4 MiB + last 4 MiB)[:16]`
     (notebook `video_fingerprint`), computed in the job handler, never in
     `/sync`.
     - The engine library is keyed by it.
     - A hit under the current signature marks the footage `ready`
       instantly: no upload, no GPU. This covers the same file in another
       project, a moved or renamed file, a copy, and an mtime-only touch.
     - Thumbs cache locally per content id.
  3. **Stage:** per-stage pickles keyed by a hash of each stage's inputs
     (notebook `Cache.stage`), under `library/<cid>/stages/`.
     - A restart or stop mid-index resumes at the last finished stage.
     - A config change reruns only the dependent stages.
     - Raw bytes are needed again only when the shots or speech stage
       misses; the library reports this as `needs_upload`.
- **Sidecar slimmed:** it keeps the registry, queue, thumb cache, tunnel,
  and search proxy. Model weights, torch, and scoring are removed.
  - Deleted: `modal_backend/`, `service/tempo_service/indexer/`,
    `storage/`, `drive.py`, `search.py`, `/drive-auth`.
  - Offline dev runs the same engine locally on CPU (notebook CPU model
    defaults) and points `TEMPO_BACKEND_URL` at it. One pipeline, one
    scoring implementation.

## Consequences

- The panel contract changes only where v4 changes data: search result
  shape, stage names, `content_id` instead of `drive_path`
  (`docs/api.md` v2).
- `format_version` is bumped to 2, so every v3 entry reindexes once through
  the content lookup.
- Upload speed is bounded by the SSH port-forward (K5).
- Search needs the instance running. A stopped instance reads as
  `BACKEND_UNREACHABLE` / tunnel down, never as a hang.
- Every machine needs the brev CLI and an org login (`brev login --token`
  for headless). This is acceptable while the operator runs the fleet.

## Revisit when

- Non-operator customers need access. Replace the tunnel with a public
  TLS endpoint behind the same `backend_url` + token seam. The panel is
  unchanged.
- A second GPU host is needed: implement `BackendProvider`.
