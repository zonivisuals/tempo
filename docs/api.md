# docs/api.md — Tempo API contracts (source of truth, v2)

Base: `http://127.0.0.1:<port>` (default `8765`, configurable). JSON only.

Errors: non-2xx with `{"error": {"code": "<SNAKE>", "message": "<human>"}}`.

Indexing and `GET /search` run on the engine (ADR-0008, contract in
`docs/engine-api.md`). The sidecar reaches it at `TEMPO_BACKEND_URL`, or
through the `brev port-forward` tunnel it supervises. The sidecar holds no
model weights.

Failures use these codes, as 502/504, and never hang:
- `BACKEND_UNREACHABLE`
- `BACKEND_ASLEEP`
- `BACKEND_TIMEOUT`

## GET /health

```json
{"status": "ok", "artifact_root": "C:\\tempo\\artifacts",
 "backend": {"reachable": true, "gpu": true, "tunnel": "up", "signature": "3f9c0a1b2d4e"}}
```
- `tunnel` is `up|down|off`. `off` means no `TEMPO_BREV_INSTANCE` is set and a direct URL is used.
- `signature` is the engine's index signature. It is empty while the engine is unreachable.

## POST /sync

Request:
```json
{"footages": [{"path": "C:\\v\\a.mp4", "size": 123, "mtime_ns": 456, "item_id": 42, "frame_rate": 25.0}]}
```
The response is immediate. Added and changed keys are enqueued right away. The job then either reuses a ready engine index for the same content, or uploads and indexes:
```json
{"added": ["a1b2"], "changed": [], "removed": [], "unchanged": [],
 "pending": [],
 "jobs": ["job_001"], "uploads": ["job_001"]}
```
Plans apply to new work only (D14). Over quota returns `403 QUOTA_EXCEEDED`
(free: 3 footage, 120 footage-minutes). Syncs with only unchanged footage always pass.

Indexing-consistency guards, which make reopening a project safe:
- Unreadable stats (`size <= 0` or `mtime_ns <= 0`) are never treated as a change.
  - Causes: a OneDrive placeholder, media still resolving when AE reopens, a missing file.
  - Unknown keys sit in `pending` until a readable stat arrives. Known keys keep their stored fingerprint (`unchanged`).
- Size/mtime drift counts as `changed` only after it repeats on consecutive
  syncs (`TEMPO_SYNC_CHANGE_CONFIRMATIONS`, default 2). Unconfirmed drift
  sits in `pending`.
- Format-version mismatches apply immediately (they are never transient).
  `pending` keys are never enqueued and never use quota.
- One active job per footage: sync and retry reuse the live job id instead of
  creating duplicates. To drop a job that hasn't started, use `POST /jobs/{job_id}/cancel` (below).
- A changed path fingerprint does not mean the content changed. The job
  derives the content id (`sha1(size + first 4 MiB + last 4 MiB)[:16]`). If
  the engine already holds a ready index for that content, it is reused: no
  upload, no GPU work. This covers moved or renamed files, copies, the same
  file in another project, and mtime-only touches.

## GET /jobs/{job_id}

```json
{"job_id": "job_001", "footage_key": "a1b2", "state": "uploading", "reused": false,
 "stages": [{"name": "upload", "state": "running", "done": 1048576, "total": 3670016},
            {"name": "shots", "state": "pending", "done": 0, "total": 0},
            {"name": "ocr", "state": "running", "done": 37, "total": 157}],
 "error": null, "reason": null}
```
- `state`: `queued|uploading|queued-for-backend|running|done|error|cancelled`.
- Stage `state`: `pending|running|done|error`.
- Stages are `upload` plus the engine's `stages` from `/v1/health`
  (`shots, visual, transcribe, ocr, captions, text, index`). The sidecar never duplicates that list.
- `reused: true` means the engine already held a ready index for this content (no upload, no GPU work).

Failed jobs keep their stage errors, and the registry entry keeps
`state: error` plus the message. Auto-sync never re-enqueues; only an explicit retry does.

### `reason` — what kind of failure, in words

`reason` is the only part of a failed job the panel renders. `error` is the raw text
for the service log and the registry entry (the engine's half of it is up to 2000
characters of traceback, `known-issues.md` S5); the panel never prints it.

Closed vocabulary, declared once as `REASONS` in `tempo_service/proxy.py`, and raised
only where the sidecar itself raises — no string is ever sniffed out of a message:

| `reason` | Raised when |
|---|---|
| `NOT_CONFIGURED` | no engine is configured to hand off to |
| `UNKNOWN_FOOTAGE` | the registry entry vanished mid-job |
| `SOURCE_MISSING` | the local file is gone (moved, deleted, drive offline) |
| `ENGINE_REJECTED` | the engine answered with an application error (4xx) |
| `ENGINE_FAILED` | the engine's own pipeline raised |
| `BACKEND_UNREACHABLE` | no route to the engine, after `backend_poll_miss_retries` |
| `BACKEND_ASLEEP` | route alive, engine not serving (the job waits instead) |
| `BACKEND_TIMEOUT` | an engine call exceeded its budget |

The last three are `tempo_service/backends/base.py`'s own codes, reused verbatim so
one failure has one name across `/search` and `/jobs`. `reason` is `null` for a job
that has not failed, and for a failure that was not one of these (any exception raised
outside `proxy.handle`).

## Authentication: none

There is no auth wall. The sidecar binds `127.0.0.1` and serves the single local
editor, so every route is public on localhost by design. (Identity was removed;
see `docs/decisions/0005-identity.md`.) The engine token `TEMPO_BACKEND_TOKEN`
is server config, never user input, and never reaches the panel.

## POST /jobs/{job_id}/retry

```json
{"job_id": "job_002", "footage_key": "a1b2"}
```
Resets the entry to `indexing` and enqueues a fresh job. An unknown id returns 404.

## POST /footage/{footage_key}/retry

Same as above, but addressed by footage key. It covers orphaned entries (service
restarted, panel reloaded, job id lost). An unknown key returns 404.
Both retry routes are idempotent while a live job exists for the key: they
return its id instead of starting a duplicate run.

## POST /jobs/{job_id}/cancel

```json
{"job_id": "job_001", "footage_key": "a1b2", "state": "cancelled",
 "stages": [...], "error": "cancelled by user"}
```
Drops a job that hasn't started yet (the worker skips it).
- Running jobs can't be stopped mid-thread: `409 NOT_CANCELLABLE`. Their completion stays valid.
- Terminal jobs return `409`.
- An unknown id returns 404.

## GET /footage

```json
[{"footage_key": "a1b2", "path": "C:\\v\\a.mp4", "content_id": "0123456789abcdef",
  "shot_count": 120, "duration_s": 600.0, "indexed_at": "2026-09-21T00:00:00Z",
  "state": "ready", "reused": false}]
```
- `state`: `uploading|indexing|ready|stale|error`.
- `content_id` is empty until the first job derives it.

## GET /search?q=&top_k=&footage_keys=

- `q` is required.
- `top_k` defaults to 8.
- `footage_keys` is an optional CSV.

Proxied to the engine (§3.5 v4 fusion), with `footage_keys` mapped to content
ids. It is budgeted with a timeout. Error codes:
- `BACKEND_ASLEEP` (also returned for the engine's `MODEL_WARMING`)
- `BACKEND_UNREACHABLE`
- `BACKEND_TIMEOUT`

`footage_key` and `source_path` come from the registry, since the engine only knows content ids.
```json
{"query": "road trip to akita", "took_ms": 41, "entities": ["Akita"],
 "results": [{"footage_key": "a1b2", "content_id": "0123456789abcdef",
   "shot_id": 119, "scene_id": 41,
   "source_path": "C:\\v\\a.mp4", "start_s": 268.2, "end_s": 274.4,
   "score": 0.512,
   "contributions": {"visual": 0.21, "dialogue": 0.11, "caption": 0.04,
                     "bm25": 0.07, "entity": 0.1, "anchor": 0.0},
   "raw_cos": {"visual": 0.118, "dialogue": 0.61, "caption": 0.55},
   "transcript": "...", "dialogue": "...", "caption": "...", "ocr": "",
   "entities": ["Akita"], "emotions": ["joy"]}]}
```
- `contributions` sum to `score`.
- `raw_cos.dialogue` is `null` for shots without dialogue.
- The panel does not render `contributions` or `raw_cos`. Result cards show thumbnail, file, timecode, and transcript/caption.
- One result is returned per scene, and results scoring ≤ 0 are dropped. Fewer than `top_k` results is expected, not an error.

## GET /thumb/{footage_key}/{shot_id}.jpg

A display keyframe JPEG with cache headers. Served over HTTP, never `file://`.
- It comes from the local cache `artifacts/thumbs/<content_id>/<shot_id>.jpg`.
  That cache is bulk-synced when a job completes and is shared by every footage with the same content.
- On a miss, the sidecar fetches the thumb from the engine and caches the bytes.
- Engine-side failures surface as `BACKEND_ASLEEP` or `BACKEND_TIMEOUT`.

## GET /host/{name}.jsx

Serves `panel/host/{json2.js,host.jsx}` verbatim (`text/plain`, `no-store`).

Loader fallback: if the panel boots with `typeof tempoListFootage !=
"function"` (CEP skipped the manifest ScriptPath evaluation), it fetches these
sources on demand and runs them with `evalScript`. Any other name returns 404.

## Panel ↔ host (ExtendScript bridge, ES3, JSON strings)

```
tempoListFootage()          → '[{"path":..., "size":..., "mtime_ns":..., "item_id":..., "frame_rate":...}]'
tempoInsertOrFocus(payload) → '{"ok":true,"comp_id":1,"layer_id":2}' | '{"ok":false,"error":"..."}'
tempoGetActiveCompInfo()    → '{"comp_id":1,"name":"...","fps":25.0}' | '{"ok":false}'
```
Payload: `{"source_path": "...", "start_s": 1.0, "end_s": 5.0}`.

Rules:
- One call does the whole job.
- Mutations are wrapped in a single `app.beginUndoGroup/endUndoGroup`.
- Locate before import (`FootageItem` + `FileSource` + `fsName`).
- `File.exists` guard.
