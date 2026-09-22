# docs/api.md — Tempo API contracts (source of truth, v1)

Base: `http://127.0.0.1:<port>` (default `8765`, configurable). JSON only.
Errors: non-2xx with `{"error": {"code": "<SNAKE>", "message": "<human>"}}`.
Colab tunnel: `GET /search` proxies to the Colab shim; tunnel failures use
codes `COLAB_UNREACHABLE`, `COLAB_ASLEEP`, `COLAB_TIMEOUT` (all 502/504, never hangs).

## GET /health

```json
{"status": "ok", "models_loaded": {"clip": false, "whisper": false}, "artifact_root": "/data/tempo",
 "colab": {"reachable": true, "gpu": true}}
```

## POST /sync

Request:
```json
{"footages": [{"path": "C:\\v\\a.mp4", "size": 123, "mtime_ns": 456, "item_id": 42, "frame_rate": 25.0}]}
```
Response (added/changed enter `uploading`, then auto-handoff to Colab; immediate):
```json
{"added": ["a1b2"], "changed": [], "removed": [], "unchanged": [],
 "jobs": ["job_001"], "uploads": ["job_001"]}
```

## GET /jobs/{job_id}

```json
{"job_id": "job_001", "footage_key": "a1b2", "state": "running",
 "stages": [{"name": "upload", "state": "running", "done": 1048576, "total": 3670016},
            {"name": "shots", "state": "pending"},
            {"name": "ocr", "state": "running", "done": 37, "total": 157}],
 "error": null}
```
`state`: `uploading|queued-for-colab|running|done|error`. Stage `state`: `pending|running|done|error`.

Failed jobs keep their stage errors and the registry entry keeps
`state: error` + message (e.g. Drive file missing with the exact
`Drive/<drive_path>` copy hint). Auto-sync never re-enqueues — explicit retry only:

## POST /jobs/{job_id}/retry

```json
{"job_id": "job_002", "footage_key": "a1b2"}
```
Resets the entry to `indexing` and enqueues a fresh job. Unknown id → 404.

## POST /footage/{footage_key}/retry

Same, addressed by footage key — covers orphaned entries (service
restarted, panel reloaded, job id lost). Unknown key → 404.

## GET /footage

```json
[{"footage_key": "a1b2", "path": "C:\\v\\a.mp4", "drive_path": "tempo/a1b2/a.mp4",
  "shot_count": 120,
  "duration_s": 600.0, "indexed_at": "2026-09-21T00:00:00Z",
  "state": "ready"}]
```
`state`: `uploading|indexing|ready|stale|error`.

## GET /search?q=&top_k=&footage_keys=

Query: `q` (required), `top_k` (default 8), `footage_keys` (csv, optional).
Proxied to Colab (same §3.5 fusion); tunneled budget with timeout —
`COLAB_ASLEEP`/`COLAB_UNREACHABLE`/`COLAB_TIMEOUT` on failure.
```json
{"query": "vending machine", "took_ms": 12,
 "results": [{"footage_key": "a1b2", "shot_id": 119,
   "source_path": "C:\\v\\a.mp4", "start_s": 268.2, "end_s": 274.4,
   "score": 0.656, "winning_key": "caption",
   "raw_cos": {"visual": 0.21, "dialogue": 0.44, "caption": 0.56},
   "contributions": {"dense": 0.351, "bm25": 0.305, "anchor": 0.0, "entity_boost": 0.0},
   "transcript": "...", "caption": "...", "entities": ["Japan"]}]}
```
- Must complete < 300 ms warm; never trigger model downloads (503 + `MODEL_NOT_LOADED` if text model missing).
- Global row order `(registry order, shot_id)` is stable across requests.

## GET /thumb/{footage_key}/{shot_id}.jpg

Keyframe JPEG with cache headers. Served over HTTP (never `file://`).
Cloud-indexed footage falls back to the Colab thumb proxy (then cached
locally); Colab-side failures surface as `COLAB_ASLEEP`/`COLAB_TIMEOUT`.

## GET /host/{name}.jsx

Serves `panel/host/{json2.js,host.jsx}` verbatim (`text/plain`, `no-store`).
Loader fallback: if the panel boots with `typeof tempoListFootage !=
"function"` (CEP skipped manifest ScriptPath evaluation), it fetches and
`evalScript`s these sources on demand. Anything else → 404.

## Panel ↔ host (ExtendScript bridge, ES3, JSON strings)

```
tempoListFootage()          → '[{"path":..., "size":..., "mtime_ns":..., "item_id":..., "frame_rate":...}]'
tempoInsertOrFocus(payload) → '{"ok":true,"comp_id":1,"layer_id":2}' | '{"ok":false,"error":"..."}'
tempoGetActiveCompInfo()    → '{"comp_id":1,"name":"...","fps":25.0}' | '{"ok":false}'
```
Payload: `{"source_path": "...", "start_s": 1.0, "end_s": 5.0}`.
Rules: one call does the whole job; mutations wrapped in a single `app.beginUndoGroup/endUndoGroup`; locate-before-import (`FootageItem` + `FileSource` + `fsName`); `File.exists` guard.
