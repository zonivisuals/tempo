# AGENTS.md — Tempo for After Effects

**Audience:** AI coding agents and human contributors working in this repository.
**Status:** v1 — ground truth for all implementation decisions.
**Rule zero:** If something in this file conflicts with the official documentation listed in §10, the documentation wins, and this file must be updated — not silently worked around.

**Build baselines (locked from scoping):** wide AE compat (only smoke-tested versions claimed), Modal-hosted pipeline behind the backend seam (Colab tunnel deleted — see D11; local indexer kept for offline dev), manual storage copy until presigned uploads land (D10 reshaped), MVP core F1–F5 (F6 minimal), Python 3.11+ pinned.

---

## 0. How to work in this repo (agent instructions)

1. Read this file fully before writing code. The architecture and contracts in §2–§4 are binding; features in §5 have acceptance criteria that define "done".
2. **No API guessing.** Every ExtendScript or CEP API call you write must be an API that already exists in this repo (proven working), or one you verified in the official docs (§10). When you verify one that wasn't used before, add a short comment citing the doc section, e.g. `// docsforadobe: CompItem.time`. If you cannot verify an API, do not use it — flag it in the PR description.
3. No regressions to the scoring contract (§3.5). The fusion formula and weights are pinned by golden tests. Changing them requires updating this file, the config defaults, and the tests in the same PR.
4. Keep changes minimal and scoped. No drive-by refactors, no reformatting of untouched files, no introducing libraries without updating §7 and this file.
5. Every PR must pass the checklist in §11.
6. Implement in phases (P0–P6, see PRODUCT.md plan). One phase per commit; never mix phases.

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
│   - search input, result cards, score bars, skeletons             │
│   - footage sync status, indexing progress, backend status row     │
│   - CSInterface.evalScript() ────► host.jsx (ExtendScript, ES3)   │
└──────────────────────────────┬────────────────────────────────────┘
         │ fetch (http://127.0.0.1:<port>)
         ▼
┌────────────────── Python Service (FastAPI, local only) ──────────┐
│  - footage registry + diff, storage-key builder (presigned later) │
│  - single-worker proxy queue: backend handoff → poll → thumb sync │
│  - search proxy, local thumb cache, backend reachability          │
└──────────────────────────────┬────────────────────────────────────┘
         │ HTTPS (server-config URL + bearer token; never user input)
         ▼
┌────────────────── Modal backend (GPU, scale-to-zero) ────────────┐
│  modal_backend/ port of the notebook stages (provenance logged)   │
│  - footage source: storage `tempo/<key>/<basename>`               │
│  - per-stage checkpoints → Volume `checkpoints/<key>/`            │
│  - search: same §3.5 fusion; serves thumbs until synced down      │
└───────────────────────────────────────────────────────────────────┘
```

Why this split (decided, do not revisit without a written ADR):
- **Pipeline on Modal, not local GPU (D11, supersedes D9):** the 9 stages need GPU RAM target machines don't have. `modal_backend/` is the deployable port (mechanical extraction, parity-tested); the notebook is the frozen behavioral reference; `search.py` + `modal_backend/scoring.py` share the golden-tested §3.5 contract. Local `indexer/` stays as the offline-dev fallback behind `backend="local"`.
- **CEP panel, not UXP:** UXP is not the supported extensibility path in After Effects; CEP is. Premiere Pro 25.6 migrated to UXP (CEP+UXP dual-support for ~1 year, then CEP removal) — AE has no such announcement as of 2026-09, and CEP 12 Cookbook still lists AEFT 25.0. Track via ADR; revisit only if Adobe announces AE UXP.
- **CEP panel, not a bare script / ScriptUI:** the product needs a real results UI (thumbnails, bars, skeletons) and a persistent docked surface.
- **Not an AE SDK (C++) plugin:** nothing here needs the render pipeline. The project API (ExtendScript) covers everything; C++ is unjustified complexity.
- **Panel cannot touch the project.** All project mutations go through `evalScript` into `host.jsx`. This is a CEP constraint, not a choice.
- **Python stays a sidecar service** because the pipeline is PyTorch/FAISS/BM25. Bound to `127.0.0.1` only. The panel degrades gracefully when it's down.

### 2.2 Repository layout

```
tempo/
├── AGENTS.md                  # this file
├── PRODUCT.md                 # product vision + scope
├── docs/
│   ├── api.md                 # full request/response schemas (source of truth)
│   └── decisions/             # numbered ADRs for anything overriding §2.1
├── service/
│   ├── pyproject.toml         # pinned deps, requires-python >=3.11
│   ├── tempo_service/
│   │   ├── app.py             # FastAPI wiring, lifespan (proxy registration)
│   │   ├── config.py          # Settings (env / config file — no hardcoding)
│   │   ├── registry.py        # footage registry, fingerprinting, diff (+drive_path)
│   │   ├── jobs.py            # single-worker proxy queue (upload → handoff → poll)
│   │   ├── drive.py           # storage-key builder (uploads land in P2)
│   │   ├── backends/          # provider seam: base (ABC+errors), http, factory
│   │   ├── search.py          # scoring exactly per §3.5 (pure) + corpus load
│   │   └── schemas.py         # pydantic request/response models
│   └── tests/                 # contract, registry, golden, pipeline, perf tests
│       └── test_search.py     # golden ordering + contributions (§3.5, §9)
├── modal_backend/             # deployable pipeline port (provenance per file)
│   ├── modal_app.py           # Modal deploy wiring (App, image, Volumes, Secret)
│   ├── modal_api.py           # backend contract app (health/index/jobs/search/thumb)
│   ├── pipeline.py            # stage orchestration + artifact persistence
│   ├── scoring.py             # pure §3.5 fusion (parity-tested vs search.py)
│   ├── _deps.py               # device probe, model names, _need() tripwire
│   ├── singletons.py          # CLIP-text + NER singletons (cell b25be17b)
│   ├── shots_visual.py        # Tier 0 shots/embeds/cluster (cell af283162)
│   ├── audio_ocr.py           # Tier 1 whisper/OCR/align (cell 6fd10aa2)
│   ├── ner.py                 # shared entity extractor (cell cfba7b76)
│   ├── enrich.py              # Tier 2 captions/NER/embeds (cell 4b9c917c)
│   └── indices.py             # FAISS + BM25 build (cell 8241b95a, no UMAP)
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
│       └── panel.js           # store + render(), polling, skeletons
└── notebook/
    └── tempo_pipeline_v3.ipynb  # reference implementation (research artifact,
                                 # NOT imported by the service — the service
                                 # re-implements it cleanly)
```

### 2.3 Cross-runtime contract rule

Panel JS (modern, Chromium) and host.jsx (ES3) are different worlds. The only channel is `evalScript(string) → callback(string)`. Therefore:

- All payloads are JSON strings. Keep them small (< ~1 MB); if ever larger, chunk. Nothing in this product needs large payloads.
- Logic lives in the panel. `host.jsx` is a thin, imperative command executor.
- No shared JS modules between panel and host. The contract lives in `docs/api.md` and is enforced by tests (§9), not by imports.

---

## 3. Python search service

### 3.1 Responsibilities

Owns: footage registry, storage-key builder, backend proxy queue, search proxy,
local thumb cache, backend reachability.
Does NOT own: the pipeline itself (Modal backend, D11), anything about
the AE project, the panel UI, undo semantics.

### 3.2 Indexing pipeline (stages)

One footage = one job = these stages, in order, each reporting progress.
Stages 1–9 run **on the backend** (`modal_backend/` port, D11); stage 0
(upload) runs locally. Progress for every stage is polled at 500 ms and
rendered by the panel (§5, F4).

| 0 | `upload` | bytes sent | — (storage provider stream, real progress; manual copy when unconfigured) |
| # | Stage | Progress unit | Model |
|---|-------|---------------|-------|
| 1 | `shots` | frames sampled | — (OpenCV + scenedetect AdaptiveDetector) |
| 2 | `visual_embed` | batches of 32 | CLIP ViT-L/14 (image) |
| 3 | `cluster` | — | KMeans, k by silhouette, 2 reps/cluster |
| 4 | `transcribe` | — | faster-whisper large-v3, word timestamps |
| 5 | `ocr` | frames | EasyOCR (edge-density prefilter) |
| 6 | `captions` | cluster reps | BLIP-2 (see caption rules below) |
| 7 | `text_embed` | — | CLIP text (dialogue + caption keys) |
| 8 | `ner` | shots | dslim/bert-base-NER via `_extract_entities` |
| 9 | `build_index` | — | BM25 corpus; matrices saved |

Rules:
- **Job queue is single-worker (proxy).** Uploads and backend handoffs run strictly sequentially. `POST /sync` may enqueue many; they process one by one. Backend asleep at handoff → job waits in `queued-for-backend` (retried each poll), never failed.
- **Backend checkpoints per stage to its Volume** (`checkpoints/<key>/`) so preemption resumes instead of restarting. Progress must reflect real work — no fake timers, ever.
- **Caption rules (locked decisions from the research pass):** canonical prompt `Question: Describe this image. Answer:`; no transcript/OCR hint (it made OPT continue the transcript instead of describing the image); `max_new_tokens=40`, `repetition_penalty=1.25`, `no_repeat_ngram_size=3`; post-clean: strip the `Question…Answer:` scaffold, collapse consecutive duplicate sentences, cap at 3 sentences (CLIP's 77-token encoder truncates anyway). Only cluster reps are captioned; all other shots inherit the nearest rep's caption (L2 on visual embeddings). Consequence (accepted): shots sharing an inherited caption share an identical caption embedding and cannot be separated by that key.
- **NER rules:** use the shared `_extract_entities` extractor on BOTH query and shot text: merge `##` subword fragments (`A`+`##kita`→`Akita`), drop 1-char and digit-only junk (a stored entity `"A"` once matched every shot containing the letter "a" through the anchor path — this class of bug is why junk filtering exists), dedupe case-insensitively. Do not re-introduce raw inline NER comprehensions.

### 3.3 Footage registry & indexing consistency

Purpose: "index every imported footage once, notice changes, forget removed ones" — without hashing gigabyte files.

- **Fingerprint** = `(resolved_path, size_bytes, mtime_ns)`. Cheap, stable enough for this purpose. Resolved via `File.fsName` on the AE side (this also normalizes OS path casing/slashes).
- **Registry** = one JSON file per artifact directory, mapping `footage_key → {fingerprint, artifact paths, format_version, stats}`. `footage_key` = deterministic short hash of the fingerprint's path component.
- **Storage link:** each entry also stores `drive_path` = `tempo/<footage_key>/<basename>` — the deterministic key the backend imports from (uploads land in P2; manual copy until then). Same key + size already stored → bytes are skipped, straight to indexing.
- **Sync flow:** panel asks host.jsx for the current project footage list (path + size + mtime + item id via `FootageItem.mainSource.file`), POSTs it to `POST /sync`; service diffs against the registry and returns: `added` (auto-enqueued for indexing), `changed` (re-enqueued), `removed` (marked stale), `unchanged` (skipped).
- **Removed footage:** artifacts are marked `stale`, not deleted. Pruning is explicit (panel button or config flag) because re-indexing is expensive and users often toggle imports. Default: manual prune.
- **Format versioning:** every artifact set carries `format_version`. On mismatch (e.g. after a scoring/captioning change), the footage is treated as `changed` and re-indexed. Bump the constant whenever artifact layout or semantics change; note it in the decisions log.

### 3.4 HTTP API contract (v1)

All under `http://127.0.0.1:<port>` (default 8765, configurable). JSON only. Errors: non-2xx with `{"error": {"code": "...", "message": "..."}}`.

```
GET  /health
     → {"status":"ok","models_loaded":{...},"artifact_root":"...",
        "backend":{"reachable":true,"gpu":true}}

POST /drive-auth
     body: {"code":"<oauth code>"}
     → {"ok":true}  (one-time consent; token cached outside the repo)

POST /sync
     body: {"footages":[{"path":"C:\\...\\a.mp4","size":123,"mtime_ns":456,
                          "item_id":42,"frame_rate":25.0}]}
     → {"added":[keys],"changed":[keys],"removed":[keys],
        "unchanged":[keys],"jobs":[job_ids],"uploads":[job_ids]}
     (added/changed enter `uploading`, then auto-handoff to the backend;
      response is immediate)

GET  /jobs/{job_id}
     → {"job_id":..., "footage_key":..., "state":"uploading|queued-for-backend|running|done|error",
        "stages":[{"name":"upload","state":"running","done":1048576,"total":3670016},
                  {"name":"shots","state":"pending"},
                  {"name":"ocr","state":"running","done":37,"total":157}],
        "error":null}

GET  /footage
     → [{"footage_key","path","drive_path","shot_count","duration_s","indexed_at",
         "state":"uploading|indexing|ready|stale|error"}]

GET  /search?q=<query>&top_k=<int, default 8>&footage_keys=<csv, optional>
     → {"query":"...", "took_ms": 12,
        "results":[{
          "footage_key":"a1b2","shot_id":119,
          "source_path":"C:\\...\\a.mp4",
          "start_s":268.2,"end_s":274.4,
          "score":0.656,
          "winning_key":"caption",
          "raw_cos":{"visual":0.21,"dialogue":0.44,"caption":0.56},
          "contributions":{"dense":0.351,"bm25":0.305,"anchor":0.0,
                           "entity_boost":0.0},
          "transcript":"...","caption":"...","entities":["Japan"]}]}

GET  /thumb/{footage_key}/{shot_id}.jpg   → keyframe image
```

Implementation notes:
- `GET /search` proxies to the backend (same §3.5 fusion, computed there).
  Budgeted, not < 300 ms over a network hop: thumbs render from the local
  cache instantly, results arrive on backend time; every fetch has a timeout
  and failures surface inline with clear codes (`BACKEND_UNREACHABLE`,
  `BACKEND_ASLEEP`, `BACKEND_TIMEOUT`) — never spinners, never hangs.
- No auth wall: the sidecar binds 127.0.0.1 for the single local editor;
  every route is public on localhost by design (identity removed, D12).
  Panel code never holds tokens. The deploy bearer token remains
  backend-to-backend only.
- Thumbnails are served over HTTP (not `file://`) — avoids CEF file-access flags entirely. Add cache headers. Thumbs + `shots.json` sync down at job completion; embeddings stay on the backend.
- `/search` may filter by `footage_keys`; global shot row order is defined as (footage registry order, then shot_id) and MUST stay stable so the stacked key matrices remain valid across requests.

### 3.5 Scoring specification (pinned — golden-tested)

```
q            = L2-normalized CLIP text embedding of the query
dense        = max(cos(q, visual_i), cos(q, dialogue_i), cos(q, caption_i))  # per shot
dense_norm   = (dense + 1) / 2
bm25_norm    = bm25_scores / max(bm25_scores)          # 0 if max <= 0
anchor_norm  = (cos(visual_i, centroid) + 1) / 2       # only if query has entities;
                                                       # centroid = mean visual emb of
                                                       # shots whose text_context
                                                       # contains a query entity
entity_boost = +0.15 iff shot.entities ∩ query.entities ≠ ∅

final = 0.45*dense_norm + 0.40*bm25_norm + 0.15*anchor_norm + entity_boost
```

- Weights live in `config.py` defaults (`DENSE_W=0.45, BM25_W=0.40, ANCHOR_W=0.15, ENTITY_BOOST=0.15`). They are configuration, not scattered literals.
- Dense scores are computed by direct matmul of the query against the three key matrices in shots_db row order. **Every per-shot value is shot-aligned by construction.** (Historical note: the original pipeline queried FAISS and discarded the returned index array — FAISS returns similarities *sorted by rank*, so assigning `scores[i] → shot i` scrambled the ranking. Never use a FAISS `.search()` result without mapping `I[]` back to shots.)
- FAISS indexes are still built and stored. They are the documented scale-up path: if the corpus grows past the point where matmul-per-query is trivial (rule of thumb: ~100k+ shots), switch the dense path to FAISS *with index mapping preserved*, behind a config flag, validated against the golden tests.
- Known calibration debt (do NOT "fix" silently): CLIP text↔text cosines (dialogue/caption keys) sit on a higher baseline (~0.5–0.7) than text↔image (~0.2–0.4), so text keys win `max()` disproportionately. Planned fix is per-key rank/z-score normalization before the max. When implemented: new `format_version`, golden-test update, entry in decisions log.
- UMAP is visualization-only and exists only in the notebook. It is not part of the service and never affects ranking.

### 3.6 Artifacts layout

```
<artifact_root>/
├── registry.json
└── footage/<footage_key>/
    ├── meta.json          # fingerprint, format_version, fps, shot count
    ├── shots.json         # per-shot: times, transcript, caption, entities…
    ├── embeddings.npz     # visual / dialogue / caption matrices (float32, L2-normed)
    ├── bm25.pkl
    └── thumbs/shot_<id>.jpg
```

Artifacts are the only durable state. The service must be restartable at any moment and resume purely from disk.

### 3.7 Configuration

`Settings` via environment variables + optional config file; documented defaults; zero absolute paths in code. Required knobs: port, artifact root, model cache dir, weights (§3.5), job poll/pacing values, `prune_stale` flag, log level, `backend` (`local|http`), `backend_url`, `backend_token` (env only), `drive_folder` (`tempo/` root), Drive chunk size, OAuth token path, `storage_provider` (`none|s3`), storage endpoint/bucket/credentials/region/TTL (env only), `storage_retention` (`delete|keep`), `plan` (`free|pro|studio`, Supabase licenses override later). Frame rates, sizes, and durations always come from data (pipeline or project), never constants. `requires-python >=3.11`.

---

## 4. CEP panel

### 4.1 Manifest & dev install

- Host id `AEFT`. Pin the version range to the AE releases you actually smoke-test and verify against the CEP Cookbook's host/version matrix — do not copy ranges from random repos. Wide-compat goal (CC 2019–2025, CEP 9–12) is allowed only for versions on the smoke checklist.
- No Node.js context (`--enable-nodejs` not used; the panel only needs `fetch`). Smaller surface, fewer failure modes.
- Dev mode: set `PlayerDebugMode` per the Cookbook (registry/plist per CSXS version — follow the Cookbook, not memory), install the `panel/` folder under the user CEP extensions folder, add `.debug` (port 8088), inspect via Chrome.
- Distribution (later): package with ZXPSignCmd per the Cookbook. Not MVP.

### 4.2 Panel ↔ host contract

`host.jsx` exposes exactly these global functions (ES3; JSON in/out; the list is closed — new capabilities mean editing this file section and `docs/api.md`):

```
tempoListFootage()            → JSON string: [{path,size,mtime_ns,item_id,frame_rate}]
tempoInsertOrFocus(payload)   → JSON string: {ok,comp_id,layer_id} | {ok:false,error}
tempoGetActiveCompInfo()      → JSON string: {comp_id,name,fps} | {ok:false}
```

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
- Backend address is server config (never panel input). `/health` reports backend reachability; unreachable/asleep renders as an honest status row, never a spinner.
- While the panel is open: poll every 2 s (config) — cheap evalScript + registry diff. New imports enter `uploading` automatically (D10), then indexing (F1).
- Explicit **Sync now** button as the manual fallback.
- While any job is running: poll `GET /jobs/{id}` at 500 ms and render the stage list (F4).

---

## 5. Feature specifications & acceptance criteria

MVP = F1–F5 core. F6 ships minimal (no slop) in MVP; full polish later.

**F1 — Automatic footage indexing (indexing consistency)**
- Import footage in AE → within one poll interval it appears in the panel as `uploading` (byte progress), then `indexing` (stage progress); on completion it becomes searchable. Zero clicks.
- Footage already indexed and unchanged → skipped (registry fingerprint match).
- Changed file (size/mtime) → re-uploaded + re-indexed; artifact format bumped → re-indexed.
- Footage removed from project → marked stale (upload cancelled); data pruned only on explicit prune. Acceptance: sync report shows added/changed/removed/unchanged counts that a human can verify against the project panel.

**F2 — Fast search + result preview**
- Enter submits. Results render as cards: keyframe thumbnail, footage name, timecode range (comp-fps timecode, from project fps), duration, transcript snippet, caption, and one Insert action. (The API still returns the decomposable score breakdown per result; the panel no longer renders it.)
- Search across all ready footage by default; footage filter dropdown when more than one footage exists. Acceptance: thumbs render from the local cache instantly; results arrive on backend time with a timeout; failures surface inline with codes (`BACKEND_UNREACHABLE`, `BACKEND_ASLEEP`, `BACKEND_TIMEOUT`). No < 300 ms bar over a network hop — the local `score_query` matmul path stays < 300 ms warm (asserted in a service test) as the contract guarantee.

**F3 — Skeleton loading while searching**
- On submit, immediately render `top_k` skeleton cards (flat gray blocks: thumb rectangle + two text lines) that pulse via opacity — no shimmer gradients, no spinners where skeletons fit.
- Skeletons never display shorter than ~200 ms (prevents flicker) and are replaced by real cards or an inline "no results" row. Errors surface as a compact inline message with the service error code — never a modal.

**F4 — Step-based indexing progress**
- Each indexing job renders its stage list (§3.2) with per-stage states: pending → running (with `done/total` progress bar where applicable) → done; error state shows the stage and message.
- The bar reflects real units (bytes sent; frames, batches, reps). Acceptance: progress updates derive from job status payloads only — no estimated/fake progress.

**F5 — Open result at exact timestamp**
- Single click on a result card performs §4.3 verbatim. Acceptance: with a comp open, after one click the layer exists, is trimmed to `[start_s, end_s]`, the playhead sits at the shot start, the layer is selected, and a single undo removes the whole action.

**F6 — UI look & feel (minimal in MVP)**
- See §6. Acceptance: a screenshot of the panel is visually at home next to native AE panels; a reviewer can flag and reject any element that reads as "AI-generated slop" per §6's list.

---

## 6. UI rules (anti-slop, binding)

Tempo's UI mimics AE native panels: dense, gray, flat, quiet. Read the host theme at startup (`CSInterface#getHostEnvironment().appSkinInfo`) and derive background/border/text colors from it; ship neutral fallbacks.

**Do:**
- Flat surfaces, 1px borders, corner radius ≤ 2px, spacing in a 4px rhythm, system font stack, 12px base size, 11px metadata.
- Monochrome + at most ONE accent color, used only for selection/active states.
- Icons: a minimal consistent set (or none — text labels are fine at this density). Every icon must be identifiable at 16px.
- Progress = thin flat bars; loading = opacity-pulsing skeletons.
- Short factual labels: "Indexing · OCR 37/157". No marketing voice anywhere.

**Don't (instant-reject in review):**
- Gradients, glows, glassmorphism, shadows-as-decoration.
- Rounded "cards" with big radii, floating chips, pill buttons.
- Purple/blue "AI product" palettes; any emoji as UI.
- Placeholder copy like "Ask anything…", "Powered by", exclamation marks.
- Spinners where skeletons belong; animated backgrounds; confetti-grade polish.
- Modals for errors; toast stacks; anything that moves that doesn't inform.

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

### 7.3 Python service
- Pinned dependencies (`pyproject.toml`, `requires-python >=3.11`); the heavy pipeline lives on the backend (D11) — the local service holds no model weights. (Local-GPU path kept for offline dev: models load lazily per stage via singletons, one worker, never all resident.)
- Pure functions for scoring (`search.py`) — no I/O inside the scoring path; matrices passed in, results passed out. This is what makes golden tests easy.
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
- Regressions against `notebook/tempo_pipeline_v3.ipynb` behavior without a golden-test update (the notebook is the behavioral reference).
- Editing vendored files (`CSInterface.js`, `json2.js`) — replace the vendored copy wholesale from upstream if an upgrade is needed, and record the version in a header comment.

---

## 9. Testing & regression policy

- **Golden search tests (service):** small synthetic corpus + recorded embeddings; pin for ~5 queries the exact result ordering and contribution values. These guard §3.5. Run in CI. When the notebook and the service disagree, write the failing case down before deciding which is right.
- **Contract tests:** every endpoint round-trips its pydantic schema; the `tempoInsertOrFocus` payload built in panel tests must satisfy the same schema fixture.
- **host.jsx smoke script:** a manual `ae_smoke.jsx` + checklist (open test project → list footage → insert at t → verify trim/playhead/undo). Runs before every release on oldest + newest claimed AE; AE cannot be UI-automated in CI cheaply — manual is the honest option.
- **Regression rule:** any user-visible behavior change ships with (a) a test change, (b) a line in the decisions log, (c) this file updated if it touches a spec above.

---

## 10. Resources (official first — these are the only authoritative sources)

**Adobe — After Effects scripting (the project API; host.jsx lives here):**
- https://docsforadobe.dev/?app=after-effects — Scripting guide: `app`, `Project`, `CompItem`, `FootageItem`, `Layer` (`startTime`, `inPoint`, `outPoint`), `Property`, `MarkerValue`, `ImportOptions`, undo groups.

**Adobe — CEP (panel platform; manifest, debug, packaging, CEF flags):**
- CEP Cookbook (provided PDF: `…/cep/cc_all/doc/documentation.pdf`) — manifest schema, `PlayerDebugMode`, `.debug`, `CEFCommandLine`, extension install folders, ZXPSignCmd, host/version matrix.
- https://github.com/Adobe-CEP — org root: `CEP-Resources` (CSInterface.js per CEP version, ZXPSignCmd), samples.
- https://github.com/Adobe-CEP/Samples/tree/master/AfterEffectsPanel — the reference panel this repo's `panel/` scaffolding is based on.

**Pipeline (service side):**
- CLIP (`openai/clip-vit-large-patch14`), BLIP-2 (`Salesforce/blip2-opt-2.7b`), faster-whisper, scenedetect, EasyOCR, dslim/bert-base-NER — respective official model/docs pages on Hugging Face / GitHub.
- faiss (wiki + getting-started), `rank_bm25` (PyPI page), `umap-learn` (readthedocs — note: visualization-only here).

**Community (useful, non-authoritative — flag as such):**
- `types-for-adobe` (pravdomil) — TS types for ExtendScript authoring comfort.
- json2.js (Crockford) — the JSON polyfill for ES3.

**Workflow rule:** before relying on any behavior not already proven in this repo, check the official source above and cite it. Stack Overflow and blog posts are leads, not references.

---

## 11. PR checklist / Definition of Done

- [ ] Reads §0–§8; change complies with every applicable spec.
- [ ] New ExtendScript/CEP APIs verified in official docs (comments cite them).
- [ ] Scoring untouched, or golden tests + §3.5 + decisions log updated together.
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
- **D3 Dense scoring via matmul, FAISS parked** — correctness first; scale path documented in §3.5.
- **D4 No context hint in BLIP-2 prompts** — hint caused transcript echo captions; dialogue key already covers transcript retrieval.
- **D5 Shared entity extractor on both query and shots** — junk entities once poisoned the anchor path ("A" matched everything); single extractor prevents query-side/index-side drift.
- **D6 Thumbnails over HTTP** — avoids CEF file-access flags; service already has the files.
- **D7 Stale-by-default pruning** — re-indexing is expensive; deletion is explicit.
- **D8 Single-GPU lazy model loading** — SUPERSEDED by D9 for MVP (kept as the documented local-GPU revival path: 8–12GB VRAM cannot hold all weights resident; load per stage, unload after, log transitions).
- **D9 Colab-hosted pipeline, local service as proxy** — SUPERSEDED by D11 (tunnel deleted; notebook kept as frozen reference — see `docs/decisions/0002-colab-remote-pipeline.md`).
- **D10 Drive auto-upload on AE import** — deterministic `tempo/<key>/<basename>`, `uploading` + `queued-for-backend` states (see `docs/decisions/0003-drive-auto-upload.md`).
- **D11 Modal-hosted pipeline behind the backend seam** — §2.1 (`modal_backend/` port, mechanical extraction with provenance; `backends/` provider interface; server-config URL + token, never user input — see `docs/decisions/0004-modal-backend.md`).
- **D12 Identity removed** — the Better Auth service, sidecar session gate, and panel sign-in were deleted (no auth wall; the localhost sidecar serves one editor). Kept as history in `docs/decisions/0005-identity.md`; reintroduce only via a new ADR.
- **D13 Storage providers, presigned uploads, raw retention** — `storage/` seam (SigV4 stdlib, botocore-parity-tested); Modal Volumes day-zero, B2 step-up, R2 later; real byte progress; raw purged post-index (see `docs/decisions/0006-storage.md`).
- **D14 Plans, entitlements, and release gates** — free tier locked (1 footage, 7 min) enforced at `/sync` (new work only, `403 QUOTA_EXCEEDED`); ruff + ESLint-ES3 gates in CI; Velopack/ZXP packaging as scripts; `docs/release.md` checklist (see `docs/decisions/0007-launch-gates.md`).

Known debt (tracked, not silently fixed):
- **K1 Key-scale calibration:** text↔text keys out-signal text↔image keys in `max()` fusion (§3.5). Fix planned: per-key normalization + `format_version` bump + golden update.
- **K2 Inherited captions:** shots sharing a rep caption share an identical caption embedding → ties within a caption group; intra-group ranking relies on the other keys. Accepted trade-off of rep-based captioning.
- **K3 Single GPU worker:** indexing is serialized; acceptable for the use case (offline, unattended).
- **K4 Backend preemption + warm search:** scale-to-zero workers resume from Volume checkpoints; search needs a warm pool (P95 latency trial before launch pricing).
- **K5 Upload bandwidth:** storage upload is the first-leg bottleneck; measured in the P10 trial.

---

*End of AGENTS.md. When in doubt: official docs, then this file, then the notebook reference — in that order.*
