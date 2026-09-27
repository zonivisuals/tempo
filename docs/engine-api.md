# docs/engine-api.md — Tempo engine contract (v1, ADR-0008)

Base: `http://127.0.0.1:<tunnel port>` on the editor machine, reached through
`brev port-forward`. The engine binds `127.0.0.1:8900` on the instance by
default. JSON only, except upload bodies and thumbs.

Errors use the sidecar envelope: non-2xx with
`{"error": {"code": "<SNAKE>", "message": "<human>"}}`.

Auth: `Authorization: Bearer <TEMPO_ENGINE_TOKEN>` on every route except
`/v1/health`. A wrong token returns `401 UNAUTHORIZED`. If no token is
configured, the engine returns `500 NO_TOKEN` (fail closed).

Every `{cid}` is a content id: 16 lowercase hex characters,
`sha1(str(size) + first 4 MiB + last 4 MiB)[:16]`. Anything else returns
`404 NOT_FOUND`.

## GET /v1/health

```json
{"status": "ok", "gpu": true, "device": "cuda", "signature": "3f9c0a1b2d4e",
 "stages": ["shots", "visual", "transcribe", "ocr", "captions", "text", "index"],
 "query_models": "ready"}
```

- `query_models`: `loading|ready|error`.
- While it is `loading`, `/v1/search` returns `503 MODEL_WARMING`.
- `signature` hashes pipeline version, models, and indexing parameters.
  Weights are excluded.

## GET /v1/library/{cid}

```json
{"content_id": "0123456789abcdef", "state": "ready", "needs_upload": false,
 "received": 0, "size": 0, "job_id": null,
 "shot_count": 179, "duration_s": 481.3, "fps": 29.97, "error": null}
```

| `state` | Meaning |
|---|---|
| `missing` | nothing known |
| `partial` | upload in progress (`received < size`) |
| `uploaded` | raw complete, not indexed |
| `indexing` | live job; `job_id` is set |
| `ready` | index valid under the current signature |
| `stale` | index from another signature |
| `error` | last job failed; `error` is set |

`needs_upload` is true when raw bytes are absent and the shots or
transcribe stage cache misses.

## GET /v1/uploads/{cid}

```json
{"content_id": "0123456789abcdef", "received": 8388608, "size": 52428800, "complete": false}
```

## PUT /v1/uploads/{cid}?offset=&size=&name=

The body is raw bytes, at most `max_chunk_mb`.
- `offset` must equal `received`; otherwise `409 OFFSET_MISMATCH` with
  `{"received": n}` in `error.message`.
- `size` is the full file size.
- `name` is used only for its extension.

When the last byte lands, the engine re-derives the content id. A mismatch
deletes the partial file and returns `422 CONTENT_MISMATCH`. On success the
response has the same shape as `GET` with `complete: true`.

## POST /v1/index

Request: `{"content_id": "0123456789abcdef"}`.

The call is idempotent:
- A live job for the content returns that job.
- If the index is already `ready`, the response is `{"job_id": null, "state": "done"}`.
- If no raw bytes exist and a source stage misses, the response is `409 SOURCE_MISSING`.

Otherwise: `{"job_id": "ejob_1a2b3c4d", "state": "queued"}`.

## GET /v1/jobs/{job_id}

```json
{"job_id": "ejob_1a2b3c4d", "content_id": "0123456789abcdef", "state": "running",
 "stages": [{"name": "shots", "state": "done", "done": 14400, "total": 14400},
            {"name": "transcribe", "state": "running", "done": 212, "total": 481}],
 "error": null, "shot_count": 0, "duration_s": 0.0, "fps": 0.0}
```

- Job `state`: `queued|running|done|error`. Stage `state`: `pending|running|done|error`.
- Progress units are real work:

| Stage | Unit |
|---|---|
| shots | frames scanned |
| visual | frames embedded |
| transcribe | audio seconds |
| ocr | keyframes |
| captions | cluster reps |
| text | steps |
| index | thumbs written |

- Envelopes persist in `jobs/<id>.json`.
- On restart, `queued` and `running` jobs are re-enqueued and resume from
  the stage cache.

## GET /v1/search?q=&top_k=&content_ids=

- `q` is required.
- `top_k` defaults to 8 (range 1–50).
- `content_ids` is an optional CSV; the default is every `ready` content.

```json
{"query": "road trip to akita", "took_ms": 38, "entities": ["Akita"],
 "results": [{"content_id": "0123456789abcdef", "shot_id": 119, "scene_id": 41,
   "start_s": 268.2, "end_s": 274.4, "score": 0.512,
   "contributions": {"visual": 0.21, "dialogue": 0.11, "caption": 0.04,
                     "bm25": 0.07, "entity": 0.1, "anchor": 0.0},
   "raw_cos": {"visual": 0.118, "dialogue": 0.61, "caption": 0.55},
   "transcript": "...", "dialogue": "...", "caption": "...", "ocr": "",
   "entities": ["Akita"], "emotions": ["joy"]}]}
```

- `contributions` sum to `score` (ADR-0009).
- `raw_cos.dialogue` is `null` for shots without dialogue.
- Errors:
  - `503 MODEL_WARMING` while query models load.
  - `503 MODEL_NOT_LOADED` if loading failed.

## GET /v1/library/{cid}/thumbs/{shot_id}.jpg

Returns one display thumb: a JPEG, `thumb_width` wide, with
`Cache-Control: public, max-age=86400`.

## GET /v1/library/{cid}/thumbs.tar

An uncompressed tar of `<shot_id>.jpg` for every shot of a `ready` content.
The sidecar syncs it down once at job completion.
