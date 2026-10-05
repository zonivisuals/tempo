# AGENTS.md — Tempo for After Effects

**Audience:** AI coding agents and human contributors working in this repository.
**Status:** v1 — ground truth for all implementation decisions.
**Rule zero:** If something in this file conflicts with the official documentation listed in §10, the documentation wins, and this file must be updated — not silently worked around.

**Build baselines (locked from scoping):** wide AE compat (only smoke-tested versions claimed), v4 pipeline + search on the Brev L4 engine behind the backend seam (D15; Modal + v3 deleted), sidecar reaches it over a supervised `brev port-forward`, direct resumable uploads into a content-addressed library (D16), MVP core F1–F5 (F6 minimal), Python 3.11+ pinned.

---

## 0. How to work in this repo (agent instructions)

1. Read this file fully before writing code. The architecture and contracts in §2–§4 are binding; features in §5 have acceptance criteria that define "done".
2. **Start of session.** Run the resume protocol in `docs/agents/session-workflow.md` before touching anything. It is five commands and it catches the failure modes that waste a session: a dirty tree from the last one, a red gate, and stale local artifacts.
3. **Orientation.** `docs/agents/orientation.md` maps every component to its files, names the seams worth testing at, and lists the dead directories still on disk that are *not* code. Read the section for your subsystem instead of re-reading the codebase. `docs/agents/known-issues.md` records verified divergences between this file and the code; read it before trusting a spec line you are about to act on.
4. **No API guessing.** Every ExtendScript or CEP API call you write must be an API that already exists in this repo (proven working), or one you verified in the official docs (§10). When you verify one that wasn't used before, add a short comment citing the doc section, e.g. `// docsforadobe: CompItem.time`. If you cannot verify an API, do not use it — flag it in the PR description.
5. No regressions to the scoring contract (§3.5). The fusion formula and weights are pinned by golden tests. Changing them requires updating this file, the config defaults, and the tests in the same PR.
6. Keep changes minimal and scoped. No drive-by refactors, no reformatting of untouched files, no introducing libraries without updating §7 and this file.
7. Every PR must pass the checklist in §11.
8. Implement in phases (P0–P6, see PRODUCT.md plan). One phase per commit; never mix phases.
9. One ticket per session. The ticket, its spec, and its blockers are the unit of work; see `docs/agents/session-workflow.md` for the loop.
10. **Commit messages are one line: `type(scope): summary`. No description paragraphs, ever.** Scope is the top-level root the commit touches — `panel`, `service`, `engine`. `docs` commits take no scope, because the type already names the root. The summary says *what changed*; the reasoning belongs in the ADR, the spec, or the PR description, not in the log. `git log --format=%B` on any commit should be a single line — if it is not, that commit is malformed.

---

## 1. Product

**Tempo** is a semantic search engine for footage inside After Effects.

The user has long video files (interviews, vlogs, rushes, documentaries). Tempo indexes them offline — shot detection, transcription, OCR, visual captioning — building three retrieval keys per shot (visual, dialogue, caption). Inside AE, a docked panel lets the editor type a natural-language query ("vending machine", "japan road trip") and get back ranked shots with thumbnails, timecodes, and a transparent breakdown of *why* each result matched. Clicking a result opens that exact range on the AE timeline at the playhead so the editor can trim precisely.

**What Tempo is not:** not a generative-AI gimmick, not a chat interface, not a cloud product. It is a dense local tool: fast, offline, transparent, undo-safe.

**Design principles (binding):**
- Every click does exactly one obvious thing. No hidden modes.
- All project mutations are undoable (single undo group per action).
- Never block the AE UI. Never block the panel UI.
- Every score shown to the user is decomposable — no black-box ranking.
- Efficiency first: indexing is expensive and done once per footage, cached; searching is milliseconds and feels instant.

---

## 2. Architecture

### 2.1 Components

```
┌──────────────────── After Effects (host: AEFT) ───────────────────┐
│  CEP Panel (HTML/CSS/JS, modern JS is OK here)                    │
│   - search input, result cards, skeletons                         │
│   - footage sync status, indexing progress, header status dot     │
│   - CSInterface.evalScript() ────► host.jsx (ExtendScript, ES3)   │
└──────────────────────────────┬────────────────────────────────────┘
         │ fetch (http://127.0.0.1:<port>)
         ▼
┌────────────────── Sidecar (FastAPI, local only, no weights) ─────┐
│  - footage registry + diff (path fingerprint → content_id)        │
│  - single-worker handoff queue: library hit | upload → index →   │
│    poll → thumbs.tar sync-down                                    │
│  - search proxy, local thumb cache, brev port-forward supervisor  │
└──────────────────────────────┬────────────────────────────────────┘
         │ http://127.0.0.1:<tunnel> + bearer token (server config only)
         │ brev port-forward tempo-l4-instance --port L:R
         ▼
┌────────────────── Engine (Brev L4, Docker Compose) ──────────────┐
│  engine/tempo_engine — v4 pipeline port (provenance per module)   │
│  - content-addressed library `library/<content_id>/`              │
│  - per-stage cache (resume + partial rebuild), durable jobs       │
│  - search: §3.5 v4 fusion, FAISS candidates, warm query models    │
│  /data = /home/ubuntu/workspace/tempo (survives brev stop/start)  │
└───────────────────────────────────────────────────────────────────┘
```

Why this split (decided, do not revisit without a written ADR):
- **Pipeline + search on the Brev engine (D15, supersedes D11):** v4 holds
  ~8 GB of GPU weights that target machines don't have. `engine/` is the
  deployable port of `tempo_pipeline_v4.ipynb`, the frozen behavioral
  reference; `engine/tempo_engine/search.py` owns the golden-tested §3.5
  contract. Offline dev runs the same engine locally on CPU (notebook CPU
  model defaults). There is one pipeline and no second scoring copy.
- **CEP panel, not UXP:** UXP is not the supported extensibility path in
  After Effects; CEP is. Premiere Pro 25.6 migrated to UXP (CEP+UXP
  dual-support for ~1 year, then CEP removal). AE has no such announcement
  as of 2026-09, and the CEP 12 Cookbook still lists AEFT 25.0. Track via
  ADR; revisit only if Adobe announces AE UXP.
- **CEP panel, not a bare script / ScriptUI:** the product needs a real
  results UI (thumbnails, bars, skeletons) and a persistent docked surface.
- **Not an AE SDK (C++) plugin:** nothing here needs the render pipeline.
  The project API (ExtendScript) covers everything; C++ is unjustified
  complexity.
- **Panel cannot touch the project.** All project mutations go through
  `evalScript` into `host.jsx`. This is a CEP constraint, not a choice.
- **Python sidecar stays local and light:**
  - It owns local paths, the registry, the thumb cache, and the tunnel. The
    engine only ever sees content ids.
  - It binds `127.0.0.1` only. The panel degrades gracefully when it's down.

### 2.2 Repository layout

```
tempo/
├── AGENTS.md                  # this file
├── PRODUCT.md                 # product vision + scope
├── eslint.config.mjs          # ES3 gate for panel/host (ecmaVersion 3 + restricted syntax)
├── package.json               # lint tooling only; pnpm + eslint 9, no panel deps
├── pnpm-lock.yaml
├── .github/workflows/test.yml # the CI gates named in §9; the source of truth for what runs
├── docs/
│   ├── api.md                 # sidecar request/response schemas (source of truth)
│   ├── engine-api.md          # engine /v1 contract (sidecar ↔ engine)
│   ├── agents/                # per-session context layer read by every new session
│   │   ├── session-workflow.md  # resume protocol, gates, the one-ticket-per-session loop
│   │   ├── orientation.md       # component → file map, seams, hot files, dead dirs on disk
│   │   ├── known-issues.md      # verified divergences between this file and the code
│   │   ├── domain.md            # vocabulary + which spec wins per topic
│   │   └── issue-tracker.md     # where tickets live and how skills reach them
│   ├── decisions/             # numbered ADRs for anything overriding §2.1
│   ├── design/                # panel-ui.md (UI spec of record) + preview.html
│   ├── ae-smoke.md            # manual AE checklist backing ae_smoke.jsx
│   ├── ui-review.md           # §6 reviewer checklist
│   ├── production.md          # deploy + runbook (see known-issues: parts are aspirational)
│   └── release.md             # pre-release gates
├── service/                   # sidecar (fastapi + pydantic only)
│   ├── pyproject.toml         # pinned deps, requires-python >=3.11
│   ├── tempo_service/
│   │   ├── app.py             # FastAPI wiring, lifespan (proxy, prober, tunnel), all routes
│   │   ├── config.py          # Settings (env / config file — no hardcoding)
│   │   ├── registry.py        # footage registry, fingerprinting, diff (+content_id)
│   │   ├── fingerprint.py     # content_id (cross-checked against the engine copy)
│   │   ├── jobs.py            # single-worker handoff queue
│   │   ├── proxy.py           # handoff: library hit | upload → index → poll → thumbs
│   │   ├── tunnel.py          # brev port-forward supervisor
│   │   ├── entitlements.py    # plan/footage/duration quotas enforced at /sync (D14)
│   │   ├── backends/          # provider seam: base (ABC+errors), http client
│   │   └── schemas.py         # pydantic request/response models
│   └── tests/                 # contract, registry, sync, handoff, tunnel, quota tests
├── engine/                    # GPU engine (Brev L4; CPU for offline dev)
│   ├── pyproject.toml         # pinned core deps + [ml] extra (torch & models)
│   ├── deploy/                # Dockerfile, compose.yaml, .env.example, brev-deploy.sh
│   ├── tempo_engine/
│   │   ├── app.py             # /v1 routes, bearer auth, lifespan (worker, warm-up)
│   │   ├── config.py          # EngineSettings + config_signature()
│   │   ├── models.py          # lazy locked singletons, device probe
│   │   ├── cache.py           # per-stage cache (notebook Cache)
│   │   ├── fingerprint.py     # content_id
│   │   ├── textproc.py        # tokenizer, NER cleanup, windows, query entities
│   │   ├── stages/            # shots, visual, speech, ocr, captions, text
│   │   ├── pipeline.py        # STAGES + build() orchestration
│   │   ├── index.py           # TempoIndex save/load + display thumbs
│   │   ├── search.py          # pure v4 fusion + FAISS candidate path (§3.5)
│   │   ├── corpus.py          # merged corpus LRU (FAISS, BM25, Gram stats)
│   │   ├── library.py         # content-addressed store + resumable uploads
│   │   ├── jobs.py            # single GPU worker, durable envelopes
│   │   └── prefetch.py        # weights → HF_HOME on the data volume
│   └── tests/                 # golden, parity, textproc, library, contract tests
├── panel/                     # CEP extension root (this folder is installed)
│   ├── CSXS/
│   │   ├── CSInterface.js     # vendored v12.0.0 (Adobe-CEP/CEP-Resources)
│   │   └── manifest.xml       # AEFT range, no nodejs, json2+host script order
│   ├── host/
│   │   ├── json2.js           # vendored 2023-05-10 (Crockford polyfill)
│   │   ├── host.jsx           # ALL project access lives here (ES3)
│   │   └── ae_smoke.jsx       # manual smoke script + docs/ae-smoke.md
│   ├── .debug                 # dev-only debug port mapping (8088)
│   └── www/
│       ├── index.html
│       ├── api.js             # single service-communication module
│       ├── panel.css
│       ├── logo.png           # the wordmark, Figma 777:761 (the one raster)
│       └── panel.js           # store + render(), polling, skeletons
├── packaging/                 # ZXP signing + Windows build scripts (not Velopack)
├── supabase/licenses.sql      # licence schema for later billing; nothing reads it yet
└── tempo_pipeline_v4.ipynb    # behavioral reference (gitignored research
                               # artifact, NEVER imported — engine ports it)
```

### 2.3 Cross-runtime contract rule

Panel JS (modern, Chromium) and host.jsx (ES3) are different worlds. The only channel is `evalScript(string) → callback(string)`. Therefore:

- All payloads are JSON strings. Keep them small (< ~1 MB); if ever larger, chunk. Nothing in this product needs large payloads.
- Logic lives in the panel. `host.jsx` is a thin, imperative command executor.
- No shared JS modules between panel and host. The contract lives in `docs/api.md` and is enforced by tests (§9), not by imports.

---

## 3. Sidecar service and engine

### 3.1 Responsibilities

**Sidecar** owns:
- the footage registry and the path → content_id mapping
- the handoff queue
- the search proxy and the local thumb cache
- the tunnel and backend reachability

It does NOT own the pipeline, scoring, model weights, anything about the AE
project, the panel UI, or undo semantics.

**Engine** owns:
- the v4 pipeline
- the content-addressed library and stage cache
- uploads and indexing jobs
- search with fusion scoring

It never sees local paths.

### 3.2 Indexing pipeline (stages)

One footage = one job = these stages, in order, each reporting progress.
- Stage 0 (`upload`) streams from the sidecar.
- Stages 1–7 run on the engine. The sidecar never duplicates their names;
  it takes them from engine `/v1/health`.
- Progress is polled at 500 ms and rendered by the panel (§5, F4).

| # | Stage | Progress unit | Model / tool (GPU default · CPU default) |
|---|-------|---------------|-------|
| 0 | `upload` | bytes sent | resumable chunked PUT, offset-checked |
| 1 | `shots` | frames scanned | scenedetect AdaptiveDetector; takes split at `max_shot_sec` (8 s); 3 frames/shot, sharpest = keyframe |
| 2 | `visual` | frames embedded | SigLIP 2 so400m-384 · base-256, mean of 3 frames |
| 3 | `transcribe` | audio seconds | faster-whisper large-v3 · small, VAD, English translation pass |
| 4 | `ocr` | keyframes | EasyOCR, full frame, edge + confidence filters |
| 5 | `captions` | cluster reps | Florence-2 large · base, `<DETAILED_CAPTION>` on KMeans medoids |
| 6 | `text` | steps | dslim/bert-base-NER, emotion classifier, bge-base-en-v1.5 embeds |
| 7 | `index` | thumbs written | index.json/npz + display thumbs |

Rules:
- **Queues are single-worker on both sides.**
  - The sidecar runs uploads and handoffs strictly sequentially; the
    engine runs one GPU job at a time (K3).
  - `POST /sync` may enqueue many jobs; they process one by one.
  - If the engine is unreachable at handoff, the job waits in
    `queued-for-backend` and is retried each poll. It never fails.
- **Stage cache.** Each stage is pickled under a hash of its inputs
  (`library/<cid>/stages/`).
  - A restart or `brev stop` mid-index resumes at the last finished stage.
  - A config change reruns only the dependent stages.
  - Progress must reflect real work — no fake timers, ever.
- **Caption rules (v4, D4 superseded):**
  - Florence-2 task `<DETAILED_CAPTION>`, `max_new_tokens=128`,
    `num_beams=3`, no sampling. No transcript/OCR hint.
  - Post-clean: strip tags, dedupe sentences, cap at 3 sentences.
  - k = caption budget (120 GPU · 40 CPU). The rep is the medoid of each
    KMeans cluster.
  - Every shot takes its nearest rep's caption. That similarity is stored
    as `caption_conf` and scales the caption key at search time (K2).
- **NER rules (D5):**
  - Use `aggregation_strategy="first"` plus span-based rebuild
    (`A`+`##kita`→`Akita`). Drop entities under 2 chars, without letters,
    or below `ner_min_score`.
  - Keep video-level canonical casing.
  - Query entities resolve against that vocabulary with typo tolerance.
  - One extractor (`textproc.clean_entities`) serves query and shots. Do
    not re-introduce raw inline NER comprehensions.
- **Dialogue key:** English words in a ±`dialogue_pad_sec` window. Shots
  under `min_dialogue_words` get no vector (`D_mask`), never a shared fake
  one.

### 3.3 Footage registry & indexing consistency

Purpose: "index every imported footage once, notice changes, forget removed ones" — without hashing gigabyte files, and without ever reindexing content the engine already holds.

- **Fingerprint** = `(resolved_path, size_bytes, mtime_ns)`. Cheap, stable enough for this purpose. Resolved via `File.fsName` on the AE side (this also normalizes OS path casing/slashes).
- **Registry** = one JSON file per artifact directory, mapping `footage_key → entry`. The entry is **flat**, not nested: `{footage_key, path, content_id, size, mtime_ns, item_id, frame_rate, format_version, state, shot_count, duration_s, indexed_at, reused}`. Transient keys (`pending_fp`, `pending_hits`, `error`) come and go; `pending_*` are cleared the moment a fingerprint resolves. There is no nested `fingerprint` or `stats` object — `registry.py` writes these keys directly. `footage_key` = first 10 hex chars of `sha1(path)`.
- **Content id (D16):** `sha1(str(size) + first 4 MiB + last 4 MiB)[:16]`.
  - Computed in the job handler, never in `/sync`.
  - The engine library is keyed by it. A ready index under the current
    signature is reused instantly: no upload, no GPU work. This covers a
    move, rename, copy, another project, or an mtime-only touch.
  - The sidecar and engine copies of the algorithm are pinned by a
    cross-check test (§8).
- **Sync flow:** the panel asks host.jsx for the current project footage
  list (path + size + mtime + item id via `FootageItem.mainSource.file`)
  and POSTs it to `POST /sync`. The service diffs against the registry and
  returns:
  - `added`: auto-enqueued
  - `changed`: re-enqueued
  - `removed`: marked stale
  - `unchanged`: skipped
  - `pending`: held, never enqueued (see below)
- **Reopen-safe guards.** A transient bad stat once queued duplicate full
  reindexes, so all three are load-bearing:
  1. Unreadable stats (`size <= 0` or `mtime_ns <= 0` — OneDrive
     placeholder, media resolving at AE reopen, missing file) are never a
     change. Unknown keys sit in `pending` until readable; known keys keep
     their stored fingerprint.
  2. Size/mtime drift counts as `changed` only after repeating on
     `TEMPO_SYNC_CHANGE_CONFIRMATIONS` consecutive syncs (default 2).
     Format-version mismatches apply immediately (config-driven, never
     transient).
  3. One active job per footage. Sync and retry reuse the live job id, and
     `POST /jobs/{id}/cancel` drops not-yet-started jobs. Running jobs
     can't be stopped mid-thread; completion stays valid.
- **Removed footage:** entries are marked `stale`, not deleted. The engine library is never pruned implicitly. Pruning is explicit because reindexing is expensive and users often toggle imports.
- **Versioning — two levels:**
  - The sidecar `format_version` (now 2) covers registry and artifact
    semantics. A mismatch counts as `changed`, and the job still reuses the
    engine index when the content matches.
  - The engine `signature` (pipeline version, models, indexing parameters;
    weights excluded) decides whether a library index is `ready` or
    `stale`.
  - Bump the right one whenever layout or semantics change, and note it in
    the decisions log.

### 3.4 HTTP API contract (v2)

Full schemas live in `docs/api.md` (sidecar, the source of truth) and `docs/engine-api.md` (engine /v1). Summary of the sidecar surface:

```
GET  /health                → {status, artifact_root, backend:{reachable,gpu,tunnel,signature}}
POST /sync                  → {added,changed,removed,unchanged,pending,jobs,uploads}
GET  /jobs/{id}             → {job_id,footage_key,state,reused,stages:[upload + engine stages],error}
POST /jobs/{id}/retry|cancel, POST /footage/{key}/retry
GET  /footage               → [{footage_key,path,content_id,shot_count,duration_s,indexed_at,state,reused}]
GET  /search?q&top_k&footage_keys → {query,took_ms,entities,results:[{footage_key,content_id,shot_id,
                               scene_id,source_path,start_s,end_s,score,contributions{6},raw_cos{3},
                               transcript,dialogue,caption,ocr,entities,emotions}]}
GET  /thumb/{footage_key}/{shot_id}.jpg → display keyframe (local cache by content_id)
GET  /host/{name}.jsx       → host.jsx + json2.js served VERBATIM for the panel's runtime
                               loader (name ∈ {json2.js, host.jsx}; anything else 404)
```

Implementation notes:
- **`GET /host/{name}.jsx`** is a dev convenience: the panel fetches `json2.js`
  then `host.jsx` over HTTP and `evalScript`s them (§2.3). It is unauthenticated
  and unverified — the bridge is the panel fetching a script and injecting it into
  AE's ExtendScript context, with no integrity check. It only works from a source
  checkout, because `app.py` resolves `panel/host/` by walking two directories up
  out of its own package. **Never expose this route on a shared host.**
- **`uploads` duplicates `jobs`.** `app.py` assigns `uploads = list(job_ids)` and
  returns both. Treat them as one field; the duplicate exists only because the
  panel reads it.
- **Error envelopes.** Every failure is `{code, message}` under an `ErrorEnvelope`.
  Sidecar codes in use: `NOT_FOUND`, `NOT_CANCELLABLE`, `QUOTA_EXCEEDED`,
  `INTERNAL` (500), plus the three backend codes below. `docs/api.md` documents
  most; `INTERNAL` and sidecar `NOT_FOUND` are currently undocumented there.
- **Search.** `GET /search` proxies to the engine, and the fusion is
  computed there.
  - It is budgeted: thumbs render from the local cache instantly, and
    results arrive on engine time.
  - Every fetch has a timeout. Failures surface inline with clear codes
    (`BACKEND_UNREACHABLE`, `BACKEND_ASLEEP`, `BACKEND_TIMEOUT`) — never
    spinners, never hangs.
- **No auth wall on the sidecar.** It binds 127.0.0.1 for the single local
  editor, and every route is public on localhost by design (identity
  removed, D12). Panel code never holds tokens. The engine bearer token is
  sidecar-to-engine only.
- **Thumbnails** are served over HTTP, never `file://`, which avoids CEF
  file-access flags entirely. Add cache headers (`public, max-age=86400`).
  Display thumbs sync down as one tar at job completion. The tar member
  filter is `\d{1,7}\.jpg` (`proxy.py`) and is the only defense against a
  hostile engine; it is asserted by `test_backends.py`. Embeddings stay on the
  engine.
- **Job and footage state vocabulary** lives in `docs/api.md:115` and
  `schemas.py`, not here. Job: `queued | uploading | running |
  queued-for-backend | done | error | cancelled`. Footage: `uploading |
  indexing | ready | stale | error`.

### 3.5 Scoring specification (pinned — golden-tested, ADR-0009)

```
qv  = SigLIP 2 text embedding of "this is a photo of {query.lower()}."  (L2)
qt  = bge embedding of BGE_QUERY_PROMPT + query                         (L2)
zpos(x, mask) = clip((x - mean_m) / std_m, 0, 3) / 3 on masked rows, 0 elsewhere;
                all-zero when |mask| < 2 or std_m < 1e-6               (population std)

visual   = zpos(V·qv)
dialogue = zpos(D·qt, D_mask)
caption  = zpos(C·qt) * caption_conf
bm25     = bm25(tokenize(query) + tokens(resolved query entities)) / max   # 0 if max <= 0
entity   = |{e ∈ query_entities : e ∈ shot.entities or \be\b in dialogue_en + ocr}| / |query_entities|
anchor   = zpos(V·l2norm(mean V[entity > 0]))   iff 0 < |entity > 0| < n, else 0

final = .35*visual + .25*dialogue + .15*caption + .15*bm25 + .10*entity + .05*anchor
rank by final desc (stable), drop final <= 0, keep one result per (content_id, scene_id), top_k
```

- Weights live in `engine/tempo_engine/config.py` defaults (`w_visual=0.35, w_dialogue=0.25, w_caption=0.15, w_bm25=0.15, w_entity=0.10, w_anchor=0.05`) along with `zscore_cap=3.0`. They are configuration, not scattered literals, and are excluded from the index signature.
- **FAISS candidates, exact statistics:**
  - Each dense key has an `IndexFlatIP` over the searched corpus
    (`IndexIDMap` over `D_mask` rows for dialogue). Top-`faiss_candidates`
    per key, plus the anchor query, BM25 hits, and entity hits, form the
    candidate set.
  - **Never use a FAISS `.search()` result without mapping `I[]` back to
    shot rows.** The original pipeline once assigned rank-sorted scores to
    shot i and scrambled the ranking.
  - Raw values for candidates are recomputed from the matrices. `mean_m`
    and `std_m` come from the corpus mean and Gram matrix (μ = q·m,
    σ² = qᵀGq/n − μ²), so z-scores are exact without a full scan.
  - With n ≤ `faiss_candidates` the result equals the notebook's
    exhaustive `search()`, pinned by a parity test. Beyond that, the
    candidate union is the approximation.
  - Scale path: HNSW behind config, then revalidate the goldens.
- Across several footages, z-scores and BM25 IDF are computed over the searched union. A single footage matches the notebook exactly.
- UMAP is visualization-only and exists only in the notebook. It is not part of the engine and never affects ranking.

### 3.6 Artifacts layout

```
sidecar <artifact_root>/
├── registry.json
└── thumbs/<content_id>/<shot_id>.jpg      # display thumbs, synced at job completion

engine <data_root>/  (= /home/ubuntu/workspace/tempo on Brev)
├── hf/                                    # HF_HOME model cache — set by compose.yaml, no code writes it
├── easyocr/                               # EasyOCR weights (its own cache, NOT under hf/)
├── uploads/<content_id>.part|.json        # in-flight resumable uploads
├── raw/<content_id>/source.<ext>          # complete upload; purged after index
├── jobs/<job_id>.json                     # durable job envelopes
└── library/<content_id>/
    ├── stages/<stage>_<deps>.pkl          # per-stage cache
    ├── frames/shotNNNNN_k.jpg             # 3 sampled frames per shot
    ├── thumbs/<shot_id>.jpg               # display thumbs (thumb_width)
    ├── thumbs.tar                         # the tar the sidecar pulls; built at index time
    ├── index.json                         # meta (signature, fps, …), shots, vocab
    └── index.npz                          # V, D, D_mask, C (float32, L2-normed)
```

Two corrections a previous revision of this file got wrong, both verified in code:
`hf/` has no Python owner (it exists only because `compose.yaml` sets
`HF_HOME=/data/hf`), and EasyOCR writes to `<data_root>/easyocr/`
(`stages/ocr.py`), a sibling of `hf/`, not a subdirectory of it.

Disk is the only durable state on both sides. Either process must be restartable at any moment and resume purely from disk.

### 3.7 Configuration

Both sides use `Settings` via environment variables. The sidecar also accepts an
optional config file; the engine is environment-only. Documented defaults, zero
absolute paths in code.

**Sidecar** (`TEMPO_`):
- port, artifact root, log level, job poll/pacing values, `prune_stale`
- `format_version`, `sync_change_confirmations`
- `backend_url`, `backend_token` (env only), backend timeouts
- `backend_health_interval_s` (15 s prober cadence), `backend_poll_miss_retries`
  (5, then the job fails), `backend_asleep_wait_s` (2 s between sleeps)
- `brev_instance`, `brev_cli`, tunnel local/remote ports and backoff
- `upload_chunk_mb`, `upload_timeout_s` (120 s per chunk)
- `plan` (`free|pro|studio`; Supabase licenses override later)
- **Known gap:** `prune_stale` is declared and has a `registry.prune_stale()`
  implementation, but nothing calls it. There is no route and `/sync` never
  invokes it. It is dead until K6 lands (see §12). Do not describe pruning as
  reachable.

**Engine** (`TEMPO_ENGINE_`):
- host, port, `data_root`, `token` (env only), `device` (`auto|cuda|cpu`)
- model overrides (empty = GPU/CPU defaults)
- indexing parameters
- weights and `zscore_cap`, `faiss_candidates`
- upload `max_chunk_mb`, `raw_retention` (`delete|keep`)
- thumb size, `preload_query_models`

Frame rates, sizes, and durations always come from data (pipeline or
project), never constants. `requires-python >=3.11`.

---

## 4. CEP panel

### 4.1 Manifest & dev install

- Host id `AEFT`. Pin the version range to the AE releases you actually smoke-test and verify against the CEP Cookbook's host/version matrix — do not copy ranges from random repos. Wide-compat goal (CC 2019–2025, CEP 9–12) is allowed only for versions on the smoke checklist.
- No Node.js context (`--enable-nodejs` not used; the panel only needs `fetch`). Smaller surface, fewer failure modes.
- Dev mode: set `PlayerDebugMode` per the Cookbook (registry/plist per CSXS version — follow the Cookbook, not memory), install the `panel/` folder under the user CEP extensions folder, add `.debug` (port 8088), inspect via Chrome.
- Distribution (later): package with ZXPSignCmd per the Cookbook. Not MVP.

### 4.2 Panel ↔ host contract

`host.jsx` exposes exactly these three **contract entry points** (ES3; JSON in/out; the list is closed — new capabilities mean editing this file section and `docs/api.md`):

```
tempoListFootage()            → JSON string: [{path,size,mtime_ns,item_id,frame_rate}]
tempoInsertOrFocus(payload)   → JSON string: {ok,comp_id,layer_id} | {ok:false,error}
tempoGetActiveCompInfo()      → JSON string: {comp_id,name,fps} | {ok:false}
```

Two more functions are declared at top level: `tempoFindFootage` and
`tempoInsertOrFocusInner`. **ExtendScript has no module scope**, so every
top-level declaration is global and reachable from `evalScript`. They are
internal helpers called only by `tempoInsertOrFocus`; the panel must not call
them. If you need a fourth entry point, add it to the list above and to
`docs/api.md` — do not add a fourth callable global and leave it undocumented.

Rules for host.jsx:
- Every mutating call is wrapped in `app.beginUndoGroup("Tempo: …")` / `app.endUndoGroup()`. One user action = one undo step. Non-negotiable.
- Locate existing footage before importing: iterate `app.project.items`, match `instanceof FootageItem` + `mainSource instanceof FileSource` + `mainSource.file.fsName === payload.path`. Never import duplicates.
- Check `File.exists` before `importFile`; return a clean error if the source is missing from disk.
- No loops with per-item `evalScript` calls; one call does the whole job.

### 4.3 Result-click → timeline behavior (spec, §5 F5)

Given a clicked result `{source_path, start_s, end_s, fps?}`:

1. Resolve/import the `FootageItem` (§4.2). Take `frameRate` from the item — the project is the single source of truth for timing display.
2. Target comp = the user's active comp if one exists (`app.project.activeItem instanceof CompItem`); otherwise create a comp matching the footage (name `"Tempo — <file base name>"`).
3. Add the footage as a layer at the current playhead time `T = comp.time`:
   ```
   layer.startTime = T - start_s          // align source t=0 so the shot begins at T
   layer.inPoint   = T
   layer.outPoint  = T + (end_s - start_s)
   ```
   (`startTime`/`inPoint`/`outPoint` are documented `Layer` properties — docsforadobe scripting guide. Verify any *additional* property in the docs before using it.)
4. Move the playhead to the shot start (`comp.time = layer.inPoint`), select the layer (deselect others), and open/raise the comp viewer if the API used is confirmed available (`CompItem.openInViewer()` — verify version support in docsforadobe before shipping; degrade silently if absent).
5. Result: the shot is on screen, exactly trimmed, playhead on its first frame, one Ctrl+Z away from gone. The editor now fine-tunes trims by hand.

This is deliberately *non-destructive and manual-trim-friendly*: Tempo places and aligns; it never locks the user out of editing.

### 4.4 Sync / polling design

AE exposes (historically) almost no CEP events to panels — do not design around nonexistent push events. Instead:

- On panel load: `tempoListFootage()` → `POST /sync`. Show diff counts.
- Engine address, token, and Brev instance are server config (never panel input). `/health` reports engine reachability and tunnel state; unreachable/asleep/tunnel-down renders as an honest status indicator, never a spinner. The indicator is the header's status dot — colour plus an `aria-label` naming the state (ADR-0012); the panel does not spell the state out in text.
- While the panel is open: poll every 2 s (config) — cheap evalScript + registry diff. New imports reuse a ready engine index or enter `uploading` automatically (D16), then indexing (F1).
- Explicit **Sync now** button as the manual fallback.
- While any job is running: poll `GET /jobs/{id}` at 500 ms and render the stage list (F4). The indexing section is a status pill and the step list, and nothing else - there is no summary line and no toggle: the list is shown whenever a job is live and disappears when none is. A failed job keeps its message and Retry visible, as does footage stranded mid-index by a service restart. While a job runs the section is the whole panel, so it is centred on both axes in a column capped at 320 px; each step row centres its own line. The pill is sized by its content and holds its position for the whole run - the step block is held at the finished list's height while a job is live, so rows arrive underneath the pill instead of pushing it down the panel. The no-footage block (frame 01) is centred on both axes the same way (`margin: auto`), and only while `#results` holds nothing else.

---

## 5. Feature specifications & acceptance criteria

MVP = F1–F5 core. F6 ships minimal (no slop) in MVP; full polish later.

**F1 — Automatic footage indexing (indexing consistency)**
- Import footage in AE → within one poll interval it appears in the panel as `uploading` (byte progress), then `indexing` (stage progress); on completion it becomes searchable. Zero clicks.
- Footage already indexed and unchanged → skipped (registry fingerprint match).
- Same content under a new path, project, copy, or mtime touch → `ready` instantly from the engine library (content id), no upload, no GPU (`reused`).
- Changed file (size/mtime, confirmed over consecutive syncs) whose content changed → re-uploaded + re-indexed; interrupted indexing resumes from the stage cache; engine signature change → rebuilt through the stage cache.
- Footage removed from project → marked stale. Acceptance: sync report shows added/changed/removed/unchanged counts that a human can verify against the project panel.
- **Known gap:** an earlier revision of this file promised "upload cancelled" on removal. It is not implemented. `/sync` marks the entry `stale` and the removal count is only logged; `jobs.cancel()` is reachable solely through `POST /jobs/{id}/cancel`. A live upload for removed footage runs to completion. Do not write a test asserting cancellation on removal until it exists.

**F2 — Fast search + result preview**
- Enter submits. Results render as cards: keyframe thumbnail, footage name, timecode range (comp-fps timecode, from project fps), duration, transcript snippet, caption, and one Insert action. (The API still returns the decomposable score breakdown per result; the panel no longer renders it.)
- Search across all ready footage by default; footage filter dropdown when more than one footage exists. Acceptance: thumbs render from the local cache instantly; results arrive on backend time with a timeout; failures surface with their codes (`BACKEND_UNREACHABLE`, `BACKEND_ASLEEP`, `BACKEND_TIMEOUT`). No < 300 ms bar over a network hop. The contract guarantee is the engine's warm ranking path (`search.rank` over a prebuilt corpus): < 300 ms at 10k shots on CPU, asserted in an engine test.

**F3 — Loading states while searching**
- On submit, immediately render `top_k` skeleton cards that pulse or sweep under the ADR-0011 motion budget. A skeleton is the design's `loading_result` (777:532) and nothing else: no card stroke and no card fill, one thumb block and one caption block, both `--r-md`, both inset by that 3px stroke so they land where the real thumbnail and caption land. The sweep's level is the design's own white 0.08 on both blocks in one token, and the caption block is the body box it stands in for (two lines of the caption's type plus the body's padding) so that no row jumps when results arrive. Detail: `docs/design/panel-ui.md` §4.1, ADR-0016.
- Skeletons never display shorter than ~200 ms (prevents flicker) and are replaced by real cards or the no-matches state block (F2/§3.1a). Errors surface with the service error code — as that block when nothing else is on screen, otherwise as a compact inline row under the search field, never a modal.

**F4 — Step-based indexing progress**
- Each indexing job renders its stage list (§3.2). A stage becomes a row when it starts running and keeps its place until it is done; the states are running → done, plus error for a stage that failed. **A stage that has not started draws no row**: the list is the running stage plus what is already finished, so a docked panel shows real progress instead of nine claims about work that has not happened, and from enqueue until the first stage reports the status pill is the only thing on screen (the space the list will fill is held, so the pill does not move when rows arrive).
- Progress is the running row's own readout in real units (bytes sent; frames, audio seconds, keyframes, reps) — there is no bar. Acceptance: progress updates derive from job status payloads only — no estimated/fake progress.
- Nine steps exist: the eight engine stages with editorial labels, plus one synthetic row bound to job `state === "queued"`, so a job the engine has not picked up is never a blank screen. Newest step at the top; a completing step slides down into place. Progress renders **no readout at all** where `total == 0` (cache-served stages, and every stage of a `reused` job) and a time count rather than a percentage for `transcribe`. Detail: `docs/design/panel-ui.md` §3.

**F5 — Open result at exact timestamp**
- Single click on a result card performs §4.3 verbatim. Acceptance: with a comp open, after one click the layer exists, is trimmed to `[start_s, end_s]`, the playhead sits at the shot start, the layer is selected, and a single undo removes the whole action.

**F6 — UI look & feel (minimal in MVP)**
- See §6. Acceptance: a screenshot of the panel is visually at home next to native AE panels; a reviewer can flag and reject any element that reads as "AI-generated slop" per §6's list.

---

## 6. UI rules (anti-slop, binding)

Tempo's UI mimics AE native panels: dense, gray, flat, quiet. Read the host theme at startup (`CSInterface#getHostEnvironment().appSkinInfo`) — but only to select dark or light; Tempo's own palette wins (ADR-0011). Ship neutral fallbacks. The visual system is the Figma design, re-measured for panel width; `docs/design/panel-ui.md` is the spec of record.

**Do:**
- Flat surfaces, 1px dividers, and the Figma design's own radii ported as ratios.
  The search field is scaled against the panel's type (13px value / 32px in the
  design = 0.406), which gives 25/196 → `--r-field: 10px`; the rest are ratios of
  their own box, so 12/560 → `--r-md: 3px` on cards and skeletons and
  10.67/60 → `--r-sm: 4px` on buttons. `--r-lg: 8px` stays on the indexing and
  empty-state pills, whose node was not re-measured and whose radius is inherited
  rather than derived. One documented exception stays round: the 7 px status dot,
  which must read as a dot. Spacing in a 4px rhythm, system font stack, 12px base /
  11px metadata.
- The design's 1.5px white→surface gradient stroke and its
  `0 8 12 rgba(0,0,0,0.2)` shadow on the search field and the pills. This is the
  one place a gradient is a surface treatment; everywhere else a gradient is only
  ever the mechanism of a loading sweep. The dark theme's stroke is `--edge`, an
  explicit `180deg` ramp: white at 0.16 down to the design's surface at 0.28
  (ADR-0015 §5). The light theme's is a flat `0.18`, so the two themes share the
  direction and not the ramp.
- Monochrome + at most ONE accent color, used only for selection/active states.
  The view-toggle chips are the design's own selected-state treatment (`777:473`):
  the active one carries the surface fill, the inactive one is bare, and the accent
  names the working view. That is a control's pressed state, not a floating chip —
  the "Don't" list below bans chips that are neither of the design's two pills.
- Icons: a minimal consistent set (or none — text labels are fine at this density). Every icon must be identifiable at 16px.
  The design's own exports are used as exported; where one is scaled to hold this
  floor (`777:473`'s 38-unit view icons render at a 19 px slot for a 16 px glyph),
  the icon slot — not the icon — is what gets resized.
  One icon is below the floor, and the exception is bounded rather than open (D22,
  ADR-0015 §2): the search field's magnifier, the design's 21×21 export taken to
  10 px - 0.476 of the export, where the type's ratio would say 8.5 - so its
  2.2751 stroke lands on 1.08 px. It is the one silhouette in the panel that
  survives the loss. A control sized rather than exported floors at 16 instead of
  scaling - the result card's insert badge is `max(16px, 18%)` of its thumbnail.
  Every other icon is at or above the floor.
- Progress is a thin readout in the running row (a percentage, or the real unit —
  MB, audio seconds). Not a bar: the design carries progress in the row's own
  text, and `total == 0` renders no readout at all.
- Short factual labels: "Reading on-screen text 37%". No marketing voice anywhere.
- Tempo ships its own **two themes** (dark + light, both derived from the
  Figma palette in `docs/design/panel-ui.md`). `appSkinInfo` no longer supplies
  background/border/text — it is read at startup only to detect which theme to
  apply. This supersedes the earlier rule that derived all three colors from
  `appSkinInfo`, which also closes the gap this section used to flag: only
  `--bg` was ever theme-derived (`panel.js` `applyTheme`).

**Don't (instant-reject in review):**
- Glows, glassmorphism, shadows anywhere other than the two pill surfaces.
- Floating chips. (The design's pills *are* the search field and the indexing
  heading; a pill that is not one of those is a chip.)
- Purple/blue "AI product" palettes; any emoji as UI.
- Placeholder copy like "Ask anything…", "Powered by", exclamation marks.
- Animated backgrounds; confetti-grade polish.
- Modals for errors; toast stacks; anything that moves that doesn't inform.
- **More than two animated surfaces on screen at once** (ADR-0011 budget).
  One named deviation: the searching frame spends three (the submit arc, the
  query shimmer, the skeleton field), and it animated all three before D24 too.
  They answer one question with one answer, which is what the rule protects;
  recorded in ADR-0017 rather than cleared here, and the shimmer is the one to
  go if the budget ever binds.
- Elements the design does not have: a result-count line above the grid, a
  separate Insert button on a card, a duplicate evalScript probe, a second
  transport module.

**Motion budget (ADR-0011, supersedes the former blanket ban):** shimmer
sweeps, indeterminate spinners and state-transition animation are permitted.
Gradients, glows and glassmorphism are permitted only as the *mechanism* of a
loading sweep, never as a surface treatment. Every animation must answer "what
state is this?" — a sweep that decorates rather than informs is rejected on the
same grounds as a spinner over a skeleton. `prefers-reduced-motion: reduce`
disables all of them (a no-op below CEF 74; see `docs/agents/known-issues.md`).

The bar: if removing an element removes information, it's good. If removing it changes nothing, delete it.

---

## 7. Coding standards

### 7.1 ExtendScript (`host.jsx`) — ES3, no exceptions
- `var` only; no arrow functions, no `let/const`, no template literals, no `Array.prototype.map/forEach`, no `JSON` (use vendored `json2.js`), no promises/async, no `fetch`.
- One function = one command; return JSON strings; throw nothing across the bridge — encode errors in the JSON (`{ok:false,error:"…"}`).
- Keep it small (< ~300 lines). If it grows, the design is wrong.
- Lint/gate with a custom ESLint `no-restricted-syntax` set in CI so modern syntax fails the build, not the review.

### 7.2 Panel JS (modern is fine)
- Chromium in CEP is modern: `fetch`, `const/let`, modules, template literals OK.
- No frameworks for MVP. No jQuery, no CSS frameworks, no bundler unless the file count forces it (then Vite, and this section gets updated).
- State is plain: a single store object + explicit `render()` calls. No reactive framework, no event bus.
- All service communication goes through one `api.js` module with typed-ish payload shapes mirroring `docs/api.md`; timeouts on every fetch; the panel must render a usable "service offline" state.

### 7.3 Python (sidecar + engine)
- Pinned dependencies (`pyproject.toml`, `requires-python >=3.11`). The sidecar holds no model weights and no ML dependencies. The engine keeps ML dependencies in its `[ml]` extra and imports them inside functions, so its core stays importable and testable on CPU CI.
- Engine models load lazily through locked singletons. Query models (SigLIP 2, bge, NER) stay resident for search; stage-only models (Whisper, EasyOCR, Florence-2, emotion) load per stage and are freed afterwards. Log load/unload.
- Pure functions for scoring (`engine/tempo_engine/search.py`) — no I/O inside the scoring path; matrices passed in, results passed out. This is what makes golden tests easy.
- Pydantic schemas for every endpoint; typed, no bare dicts crossing layers.
- No `print` debugging in committed code; `logging` with levels; log job stage transitions + model load/unload.
- No hardcoded paths, ports, URLs, weights (weights: config defaults, §3.5), model names, or magic numbers. If a literal appears twice, it's a constant.

### 7.4 No-hallucination policy for APIs (repeat of rule zero, operationalized)
- ExtendScript/CEP APIs already used in this repo: fine.
- Anything new: verify in docsforadobe / the CEP Cookbook; cite in a comment.
- Unsure → don't ship it; open a note in the PR with the doc section you checked. "It probably exists" is a rejected PR.
- Community resources (`types-for-adobe`, boilerplates) may inform but never substitute for the official docs.

---

## 8. Prohibited (repo-wide)

- Fake progress, fake latency, decorative animations, dark-pattern UX.
- Hardcoded machine-specific paths, ports, or model names in logic.
- Duplicated constants that must stay in sync (panel/host/python) — either derive from data, from config, or pin them with a cross-check test.
- New heavyweight dependencies without a written rationale in the PR.
- Dead code, commented-out blocks, TODOs without an owner/issue.
- Regressions against `tempo_pipeline_v4.ipynb` behavior without a golden-test update (the notebook is the behavioral reference; engine modules name their source cell).
- Editing vendored files (`CSInterface.js`, `json2.js`) — replace the vendored copy wholesale from upstream if an upgrade is needed, and record the version in a header comment.

---

## 9. Testing & regression policy

- **Golden search tests (engine):** small synthetic corpus + recorded embeddings; pin the exact result ordering and contribution values. A parity test pins FAISS candidates == the notebook's exhaustive search when n ≤ `faiss_candidates`, and Gram-matrix z-stats == `np.std`. These guard §3.5. Run in CI. When the notebook and the engine disagree, write the failing case down before deciding which is right.
- **Engine contract tests:** a fake pipeline drives index → poll → done, plus resumable upload offsets, content-id verification, search shape, thumbs, and auth. The sidecar handoff is tested against a fake provider for library reuse, resumed upload, and thumb sync-down.
- **Contract tests:** every endpoint round-trips its pydantic schema; the `tempoInsertOrFocus` payload built in panel tests must satisfy the same schema fixture. **Known gap:** the panel side is only a substring check against `panel.js` source text (`test_contracts.py:85-89`), not a shared fixture. There is no test for `GET /host/{name}.jsx`.
- **Running the engine suite locally** needs the package on the path first (`pip install "./engine[dev]"`). Without it every test errors with `ModuleNotFoundError: No module named 'tempo_engine'`. The sidecar suite has no such requirement.
- **`test_warm_rank_under_300ms_at_10k_shots` (F2) is order-sensitive.** It passes in isolation and fails when the full engine suite runs first, because the preceding tests leave the process memory-bound. Measured ~157 ms median against a 300 ms budget. Do not chase this as a scoring regression; re-run it alone to confirm.
- **host.jsx smoke script:** a manual `ae_smoke.jsx` + checklist (open test project → list footage → insert at t → verify trim/playhead/undo). Runs before every release on oldest + newest claimed AE; AE cannot be UI-automated in CI cheaply — manual is the honest option.
- **Panel screens without AE:** `docs/design/preview.html` opens by double-click and renders every panel screen against the real `panel.css` and `panel.js`, stubbing only `CSInterface` and `TempoAPI`. Screens are deep-linkable (`preview.html#indexing`). `test_contracts.py` pins the preview's copied markup against `index.html`, and `test_panel_js_evaluates_cleanly` runs `panel.js` through `vm.runInThisContext` — `node --check` is parse-only and would pass a file that throws on load.
- **Regression rule:** any user-visible behavior change ships with (a) a test change, (b) a line in the decisions log, (c) this file updated if it touches a spec above.

---

## 10. Resources (official first — these are the only authoritative sources)

**Adobe — After Effects scripting (the project API; host.jsx lives here):**
- https://docsforadobe.dev/?app=after-effects — Scripting guide: `app`, `Project`, `CompItem`, `FootageItem`, `Layer` (`startTime`, `inPoint`, `outPoint`), `Property`, `MarkerValue`, `ImportOptions`, undo groups.

**Adobe — CEP (panel platform; manifest, debug, packaging, CEF flags):**
- CEP Cookbook (provided PDF: `…/cep/cc_all/doc/documentation.pdf`) — manifest schema, `PlayerDebugMode`, `.debug`, `CEFCommandLine`, extension install folders, ZXPSignCmd, host/version matrix.
- https://github.com/Adobe-CEP — org root: `CEP-Resources` (CSInterface.js per CEP version, ZXPSignCmd), samples.
- https://github.com/Adobe-CEP/Samples/tree/master/AfterEffectsPanel — the reference panel this repo's `panel/` scaffolding is based on.

**Engine host — NVIDIA Brev:**
- https://docs.nvidia.com/brev/latest/ — GPU instances (lifecycle, `/home/ubuntu/workspace` persistence), GPU types (L4 22 GB), custom containers (compose GPU reservation), CLI connectivity (`brev port-forward <inst> --port L:R`, `brev exec`), console reference (tunnels need browser auth → API clients use port-forward). Index: https://docs.nvidia.com/brev/llms.txt.

**Pipeline (engine side):**
- SigLIP 2 (`google/siglip2-so400m-patch14-384`, transformers `model_doc/siglip2`), Florence-2 (`florence-community/Florence-2-large`, transformers `model_doc/florence2`), bge (`BAAI/bge-base-en-v1.5`, query instruction), faster-whisper (VAD; turbo cannot translate — issue 1237), scenedetect (`detect_scenes(duration=)` continues from the current position — verified in-repo against a single pass), EasyOCR (language compatibility), dslim/bert-base-NER, `j-hartmann/emotion-english-distilroberta-base`, transformers `TokenClassificationPipeline` (`aggregation_strategy`) — respective official model/docs pages on Hugging Face / GitHub.
- faiss (wiki + getting-started), `rank_bm25` (PyPI page), `rapidfuzz` (`distance.OSA`).

**Community (useful, non-authoritative — flag as such):**
- `types-for-adobe` (pravdomil) — TS types for ExtendScript authoring comfort.
- json2.js (Crockford) — the JSON polyfill for ES3.

**Workflow rule:** before relying on any behavior not already proven in this repo, check the official source above and cite it. Stack Overflow and blog posts are leads, not references.

---

## 11. PR checklist / Definition of Done

- [ ] Reads §0–§8; change complies with every applicable spec.
- [ ] New ExtendScript/CEP APIs verified in official docs (comments cite them).
- [ ] Scoring untouched, or golden tests + §3.5 + decisions log updated together (engine signature bumped if index semantics changed).
- [ ] No new hardcoded paths/ports/weights/names; config covers it.
- [ ] host.jsx mutations are undo-grouped; no duplicate imports possible.
- [ ] Panel renders offline-service and error states; no modals.
- [ ] UI follows §6 (reviewer explicitly checks for §6 "Don't" items).
- [ ] Progress indicators reflect real job status only.
- [ ] Tests added/updated (golden, contract, or smoke checklist) and green.
- [ ] This file updated if behavior/spec changed.

---

## 12. Decisions log & known debt

Decisions (with rationale; changes require an ADR in `docs/decisions/`):
- **D1 CEP panel + host.jsx + Python sidecar** — §2.1 (UXP unsupported in AE; re-check if Adobe announces AE UXP — see `docs/decisions/0001-ae-uxp-watch.md`).
- **D2 Polling for project sync** — AE exposes ~no CEP events; polling is the reliable primitive. Revisit only if the Cookbook documents AEFT events.
- **D3 Dense scoring via matmul, FAISS parked** — SUPERSEDED by D17 (FAISS candidates with exact Gram-matrix z-stats, parity-tested against the exhaustive path).
- **D4 No context hint in caption prompts** — the hint caused transcript-echo captions. It still holds for Florence-2 (`<DETAILED_CAPTION>`, image only). BLIP-2 was retired by D17.
- **D5 Shared entity extractor on both query and shots** — junk entities once poisoned the anchor path ("A" matched everything); single extractor prevents query-side/index-side drift. v4: `first` aggregation + span rebuild + typo-tolerant vocabulary resolution (ADR-0009).
- **D6 Thumbnails over HTTP** — avoids CEF file-access flags; service already has the files.
- **D7 Stale-by-default pruning** — re-indexing is expensive; deletion is explicit.
- **D8 Single-GPU lazy model loading** — revived on the engine: query models stay resident, stage-only models load per stage and are freed afterwards, transitions logged.
- **D9 Colab-hosted pipeline, local service as proxy** — SUPERSEDED by D11 (tunnel deleted; notebook kept as frozen reference — see `docs/decisions/0002-colab-remote-pipeline.md`).
- **D10 Drive auto-upload on AE import** — deterministic `tempo/<key>/<basename>`, `uploading` + `queued-for-backend` states (see `docs/decisions/0003-drive-auto-upload.md`).
- **D11 Modal-hosted pipeline behind the backend seam** — SUPERSEDED by D15 (`modal_backend/` deleted; the `backends/` seam and server-config URL + token kept — see `docs/decisions/0004-modal-backend.md`).
- **D12 Identity removed** — the Better Auth service, sidecar session gate, and panel sign-in were deleted (no auth wall; the localhost sidecar serves one editor). Kept as history in `docs/decisions/0005-identity.md`; reintroduce only via a new ADR.
- **D13 Storage providers, presigned uploads, raw retention** — transport SUPERSEDED by D16 (`storage/` deleted, direct resumable upload to the engine); raw-purge-after-index retention kept (see `docs/decisions/0006-storage.md`).
- **D14 Plans, entitlements, and release gates** — free tier locked (3 footage, 120 min — footage 1→3 and minutes 7→120 by ADR-0010) enforced at `/sync` (new work only, `403 QUOTA_EXCEEDED`); ruff + ESLint-ES3 gates in CI; Velopack/ZXP packaging as scripts; `docs/release.md` checklist (see `docs/decisions/0007-launch-gates.md`).
- **D15 Brev L4 engine behind the backend seam** — `engine/` runs the v4 pipeline and search in Docker Compose on `tempo-l4-instance`, bound to the instance's localhost, reached through the sidecar-supervised `brev port-forward`, bearer token on every route but health (see `docs/decisions/0008-brev-engine.md`).
- **D16 Content-addressed cache** — three layers: path fingerprint (registry), content id (engine library, instant reuse), and per-stage cache (resume and partial rebuild); resumable offset-checked uploads; display thumbs synced down per content id (ADR-0008).
- **D17 v4 pipeline + z-score fusion** — SigLIP 2 / bge / Florence-2 / VAD Whisper; six-component weighted fusion with per-key z-scores; FAISS candidates with exact statistics; one result per scene (see `docs/decisions/0009-v4-pipeline.md`).
- **D18 Figma-derived panel UI** — the Figma design ported (radii as ratios, its gradient strokes and shadow, its two-arc indeterminate indicator, shimmer and state-transition motion under a two-surface budget); type re-derived for panel scale; Tempo ships its own two themes and `appSkinInfo` only selects one; step list keyed, not re-rendered, and a stage that has not started draws no row. The indexing screen later lost its summary line and gained centring (§4.4): the pill and the started stages are the whole screen, so it is centred in a capped column rather than stacked under the status bar. The pill is then sized by its content rather than spanning that column, and the centring resolves against a fixed height - the step block is held at the finished list's height while a job is live, so the pill and the running row stay put and only completed rows move. Every indeterminate indicator is the accent arc over a white track (`--spin-track`), not a dimmed `currentColor` that composited to gray; the light theme overrides the track, white being invisible on it. Frame 01 then took the same centring, so the no-footage block sits in the middle of the panel rather than under the status bar, and only while `#results` holds nothing else. Spec in `docs/design/panel-ui.md` (see `docs/decisions/0011-figma-panel-ui.md`).
- **D19 The wordmark header** — the navbar's `Tempo` text mark is replaced by the
  real `tempo_logo` (`panel/www/logo.png`, Figma `777:761`, a raster image fill,
  so it ships as an asset rather than traced geometry — §8 forbids an invented
  mark; 280×49 at `height: 14px`, which is exactly 80px wide, with the three-way
  agreement between the PNG header, the CSS and the `<img>` pinned by a test).
  `#statusbar` becomes `#topbar` and keeps only what §4.4 binds there: the status
  dot and the Sync now fallback. The state labels the bar spelled out
  (`service ok`, `engine gpu`, …) were a second rendering of what the dot already
  encoded, so they became the dot's legend — one `backendState()` cascade returns
  the class and the label together, so the colour and the words cannot disagree —
  and the dot lost `aria-hidden`, because with the text nodes gone it is the only
  carrier of that state. The light theme filters the near-white raster
  (`invert(1) hue-rotate(180deg)`) rather than carrying a second asset, which
  keeps both accents' hue where a plain invert would leave them cyan. The honest
  status of §4.4 is now a hover (or a screen reader) away rather than always on
  screen; the error row still surfaces the codes inline. Spec in
  `docs/design/panel-ui.md` (see `docs/decisions/0012-wordmark-header.md`).
- **D18 addendum — the view pair is `777:473` again, and it is on the left.** The
  grid/list pair had drifted to the right edge of `#searchmeta` and been redrawn as
  16-unit icons in 24px chips, so neither its placement nor its geometry was the
  design's. It is now flush left on the card grid (the line the design puts it on:
  in the render, the chip and the first card both start at x=124, the search field
  at x=88), at the design's ratios rather than its pixels — 32px chip, `--r-sm`
  exact at 0.125, 8px gap at 0.25, and a 19px icon slot, which is 38/64 of the chip
  and lands the export's 32-unit glyph on exactly 16px. That last number is the
  reason the chip grew instead of only moving: the same 38-unit asset in the old
  24px chip renders a 13.5px glyph, under §6's floor. The icons are the design's
  own path data, including the list icon's three bullets, which are zero-length
  segments `stroke-linecap: round` draws as dots — flattening them to three bare
  rules is the thing that was wrong before. Active view is the chip fill, as drawn,
  so the inactive chip is `transparent` rather than a second identical fill; §6's
  accent still names the working view. Spec in `docs/design/panel-ui.md` §1.
- **D20 The panel scales by type, not by frame geometry.** The port had been
  claiming one method and using another: the submit button is 60px in the design
  and 24px in the panel (0.4), and the panel's 13px search value against the
  design's 32px is 0.406 — the same ratio. §1's prose said the field scaled
  against the frame, which is a method that cannot work in either direction: the
  design's field is 10.7% of its content width and the panel's was already 18%,
  so every frame ratio argued for shrinking the one control that was too tight.
  The search field's spacing is now re-derived on the 4px rhythm from `815:294`'s
  measured 47 / 46 / 53 of padding and label-to-value gap (× 0.406 → 20 / 20 / 20,
  side padding 16, icon-to-label 6), which takes it from 57px to 107px. The rows
  are set by the icon (21px) and the submit button (24px), not by the text, and
  the arithmetic says so. Its corrected radius 25/196 × 0.406 = 10.2px gets
  `--r-field`, split from `--r-lg` so the field's measurement cannot move the
  indexing and empty-state pills, whose own node (`777:698`) was never measured.
  §1's icon rule becomes a floor rather than a size, because the design's 21px
  magnifier at 0.406 would be a grey smudge under §6's own 16px line.
  `Search for anything` is kept, reversing §3.1's drop: §6 bans *placeholder*
  copy, and the design draws it as a permanent field label, which is a different
  thing the earlier reading conflated. The header's `border-bottom` hairline goes,
  since the design has never had one. Spec in `docs/design/panel-ui.md` §1
  (see `docs/decisions/0013-search-field-scale-and-spacing.md`).
  **Amended by D22**, which reverses the 107px spacing (now 82px) and the 21px
  magnifier (now 10px). The scale basis and the method are untouched; the two
  numbers and the icon's exemption are not.
- **D21 The grid card body is two columns.** `777:368`'s caption-and-duration row is a 500px shape; in a grid cell it is 122px and the two strings read as unrelated labels. The grid body is re-derived — the description is the left column, spanning both rows and centred, and duration plus file name are the right column on the body's bottom edge — while the list view keeps the design's row verbatim, since a full-width cell is what that shape was drawn for. The list's `.cardrow` wrapper is dissolved under `#results.grid` with `display: contents`, so this is CSS only: the markup and DOM order are unchanged, and no element in the card body carries a `role` or ARIA, so the wrapper has no semantics to lose. Three details are load-bearing. The description spans with `grid-row: 1 / -1`, and the rows are declared explicitly because `-1` is the end of the *explicit* grid: with implicit rows the span collapses and the description centres inside the name's line, which is exactly what the first version did — measured at 9px above centre while every declaration assertion still passed, because those tests pin text and not geometry. The name is row 1 and the duration row 2, because the *name* is the optional line (it renders only when more than one footage is loaded): the empty row then falls above the duration, which stays on the bottom edge, and reversed it would fall below and lift the duration off it in the common single-footage case; `:has()` would say this directly and is Chromium 105 against the panel's real floor of 84. The duration is not "the line that always exists" — `renderResults` gates the whole `.cardrow` on a non-empty description, so a shot with neither caption nor transcript renders the name alone, which the test pins. The metadata track is a definite `5em`, not `auto`, which would size to max-content first and starve the description instead of ellipsizing the name. Consequence, accepted knowingly: a grid description is about 11 characters per line and a name ellipsizes at nine. Spec in `docs/design/panel-ui.md` §4.2 (see `docs/decisions/0014-grid-card-body-columns.md`).
- **D22 The panel's chrome is re-derived, and three reversals with it.** The search field's spacing goes from ADR-0013's 20 / 20 / 20 to 16 / 16 / 8, which takes it from 107px to 82px — 107px is over a third of a 300px viewport before a single result. The label row changes owners as a consequence: it used to be set by the 21px magnifier, and at 10px it is the 11px label text at 1.45 instead, so the field's own arithmetic had to be recomputed rather than re-listed. The magnifier takes the scale ADR-0013 exempted it from — 10px, where the design's 2.2751 stroke lands on 1.08px — and §6's 16px icon floor now names it as the one bounded exception. The view pair's chips touch: the design's 16-of-64 gap is gone and the pressed fill is the only separator, so the pair reads as one 64px control, which is the trade. Two changes have no reversal in them: the thumbnail takes `--r-md`, which §1 has always claimed for it and the rule never declared, and the insert badge is now the circle-plus at `fill="currentColor"` with `color: var(--accent)` — one owner for the accent instead of a literal hex that would be wrong on the light theme — sized `max(16px, 18%)` of its thumbnail, because the thumbnail is the grid cell's width in one view and a fixed 72px in the other. The 18% is derived from the 300px dock, not read off the design: the badge is the one asset in the panel whose box is unmeasured, and Figma's read endpoints were rate-limited throughout the session. `--edge` becomes an explicit `180deg` ramp, white 0.16 → surface 0.28, so the dark theme's edge catches light from above the way the design's vertical paint does; the light theme's was already a `180deg` ramp, so the two now share a shape but not a ramp (its own is a flat 0.18). Spec in `docs/design/panel-ui.md` §1 and §4.2 (see `docs/decisions/0015-panel-chrome-re-derived.md`).
- **D23 The searching frame is the design's two blocks and nothing else.** `loading_result` (777:532) is a transparent 560x399 frame with no fill and no stroke, holding `thumb-sk` (554x312 at x=3, radius 12) and `cap-sk` (560x69, radius 12) with the same fill on both. The panel had inherited the result card's 3px stroke and `--surface` fill, so the loading state was a grey card with two dimmer rectangles in it; both go, and the blocks take over the job the stroke was doing - the 3px inset *is* that stroke's width, which is what lands them exactly where the real thumbnail and the real caption land. Both blocks are `--r-md`, the same 12 of 560 the card has. The sweep's level is the design's own white 0.08, identical on both blocks, so `--sweep-thumb` (0.56) and `--sweep-cap` (1.0 - a pure white, the brightest pixel on a dark card) collapse into one `--sweep`; the design saying the two are equal is what makes it one token. The one number that could not be copied is the cap's height: the design's 69 is its body box at 20px caption type, and type is re-derived rather than scaled, so the panel's same box is 2 x 11px at 1.45 plus the body's 6px either side = 44. Taken literally it would be 17px and every row would jump ~30px when results land, which is what §4.1's "the list does not reflow on submit" exists to prevent. Two consequences worth naming: `.card:hover` paints the accent and a `div` still matches `:hover`, so the skeleton needs its own guard now that it has no fill to lose, and the blocks' resting `background-position` is the keyframe's end state so `prefers-reduced-motion` shows a centred peak instead of a left-pinned ramp. Spec in `docs/design/panel-ui.md` §4.1 (see `docs/decisions/0016-searching-frame-two-blocks.md`).- **D24 The query value shimmers as one text layer.** The searching field painted the query twice - a legible `#q-base` with a band over the top of it - on a gradient with no `no-repeat`, so the editor saw a full-strength query with a second edge crossing it. That double layer *is* the noise: `#q-base` is deleted, and the gradient's own outer stops are the resting colour, which is how shadcn/ui's `shimmer` utility does it. Its geometry is ported verbatim - the 20deg tilt (so the gradient is `110deg`), the `calc(3ch + 40px)` spread, and the `calc(200% + spread * 2)` sizing whose `2 *` is what keeps the band clear of both ends so the loop never wraps - and its colours are its own formula run over this panel's tokens rather than picked: the utility derives its highlight from `currentColor` (lightness +0.4, alpha +0.4 in its dark variant), and over `--text-dim`'s 0.4 that lands exactly on `--text`'s 0.8, with the mid stop their half-mix. The utility reaches that through `oklch(from currentColor ...)` and `color-mix()`, far above the Chromium 84 floor of ADR-0014, but the two levels it lands on are tokens the panel already has - so the base and the peak are written as `var(--text-dim)` and `var(--text)` rather than as literals of their own alphas (§7.3), and only `--qsweep-mid` - the half-mix, which nothing derives - stays a literal: one `--qsweep` shape for both themes, the light one overriding that single token. The band is **not** the accent: ADR-0011 gave it `--accent`, which §6 fences to selection and active states and a search in flight is neither, and the light theme's per-element override goes with it because `--text-dim`/`--text` already flip. It runs right to left - the direction the skeleton sweep already uses - at 1 s. That is *not* reconciled with the skeleton sweep: the band travels `W + 2 x spread` per cycle on the mirror's shrink-to-fit text width, so its speed moves with the query's length (~150 px/s at three characters, ~320 px/s at a full 200px field) against the skeletons' fixed ~220 px/s. The two surfaces are not meant to read as one animation, and the figure is recorded so no later reader quotes it as a constant or "fixes" it as an inconsistency. Reduced motion is a **fix as well as a decision**: `animation: none` alone parked the band clear of the string and left the field blank mid-search, so the query now gives the gradient up and takes `--text` back - the utility's own answer, and the reason that rule is its own instead of part of the animation-only list. The skeleton blocks keep ADR-0016's resting-position answer, because their resting state is a shape and not text. The searching frame animates three surfaces where §6's ceiling is two (submit arc, query shimmer, skeleton field) and animated all three before this change; §6 now names it as a recorded deviation rather than leaving a reviewer to find it, and the shimmer is the one to go if the budget ever binds. Spec in `docs/design/panel-ui.md` §3.4 and §4.1 (see `docs/decisions/0017-query-shimmer-one-layer.md`).

- **D25 One state block for everything with nothing to show, and one cascade that says which of the two speaks.** Two screens had two shapes for the same fact. The no-matches screen was one `--dim` sentence in a bare div at the top of the results area while frame 01 - one rung further down the same ladder - had been a centred block since D18, so "there is nothing here for you" was rendered twice in unrelated shapes; and the three failure screens were a 11px `--error` row pinned under the header, which is right for a failure arriving *over* content and wrong for a panel whose whole report of an outage was `SERVICE_OFFLINE` in code where a sentence belonged. So frame 01's block is now the shape for every state with nothing to show - no footage and its four variants (wording unchanged), a search that matched nothing, the screen before any search, and a failure - and `resultsScreen()` is the only question about which, read by `renderResults` and `renderError` alike, because the two used to derive it separately (ready footage vs. error exists) and could disagree. Two precedence rules in it are load-bearing: `error` requires an empty result set, because the block would otherwise wipe results the editor is still reading (a failed insert is no reason nine cards disappear), and `error` sits *above* the no-footage branch, because with the service down "no footage found" is a claim about the project the panel cannot make - it does not know whether the project has footage, it knows it could not ask. Each failure now names itself in words and says what to do, with the service's code on a third `.detail` line, since a code in the heading is a label and F2 requires the code on screen; an unnamed new code falls back to the message as its instruction rather than to nothing, and both routes are clamped, because a job error is 2000 characters of traceback and a block that tall is not a message. `QUOTA_EXCEEDED` is the one state that also quotes the service's own sentence, because the numbers are the useful part and §7.3 keeps a plan limit out of the panel - its instruction says footage already indexed stays searchable, since a denial on `/sync` gates new work only. The block is `--accent` like every other block - `--error` stays on the header dot and the retained row, which is now only for errors over content. Quoting the query made `overflow-wrap` load-bearing on the hint (`max-width` alone does not stop one long query widening the block past the panel), `.empty` went with its only user, and the block adds no animation, so D18's motion budget is untouched. Spec in `docs/design/panel-ui.md` §3.1a, §3.1b, §6 (see `docs/decisions/0018-failure-state-block.md`).

Known debt (tracked, not silently fixed):
- **K1 Key-scale calibration:** RESOLVED by D17 (per-key z-scores before a weighted sum).
- **K2 Inherited captions:** shots sharing a rep caption share an identical caption embedding. `caption_conf` (similarity to the rep) now scales the key, so ties only remain between equally close shots. Accepted trade-off of rep-based captioning.
- **K3 Single GPU worker:** indexing is serialized; acceptable for the use case (offline, unattended).
- **K4 Instance uptime:** search needs `tempo-l4-instance` running (billed per hour). A stopped instance surfaces as tunnel down / `BACKEND_UNREACHABLE`. Indexing resumes from the stage cache after `brev start`.
- **K5 Upload bandwidth:** uploads ride the SSH port-forward; this is the first-leg bottleneck, measured in the Brev trial.
- **K6 Engine library pruning:** the engine keeps every content index until it is deleted explicitly (stale is local-only). There is no prune route yet; disk is watched on the instance.

---

*End of AGENTS.md. When in doubt: official docs, then this file, then the notebook reference — in that order.*
