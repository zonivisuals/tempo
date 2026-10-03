# Orientation

Read your section, not the codebase. This file maps every component to its files,
names the seams worth testing at, and lists the dead directories on disk that are
not code.

Line counts are from the last verified pass. They are there to size a read, not as
a contract; `git log --oneline -5 -- <path>` is the authority for "is this current".

## Read order by task type

| Your task | Read, in this order | Stop when |
|---|---|---|
| Anything at all | `AGENTS.md` §0, then this file, then `known-issues.md` | you can name the files you'll touch |
| Touch `search.py` or scoring | `AGENTS.md` §3.5 → `engine/tempo_engine/search.py` → `corpus.py` → `engine/tests/test_search.py` | you can recite the six components and their weights |
| Change an endpoint | `docs/api.md` (sidecar) or `docs/engine-api.md` (engine) → the `app.py` route → `schemas.py` → the matching contract test | you know the response shape and the auth requirement |
| Change sync or registry behavior | `AGENTS.md` §3.3 → `registry.py` → `service/tests/test_registry.py` and `test_sync.py` | you know which of the three reopen guards you are touching |
| Touch the panel | `AGENTS.md` §4 and §6 → `panel/www/api.js` → `panel/www/panel.js` → `panel/host/host.jsx` | you know which side of the evalScript bridge you are on |
| Touch `host.jsx` | `AGENTS.md` §4.2 and §4.3 → `panel/host/host.jsx` (147 lines, read all of it) → `eslint.config.mjs` | you can state the undo-group boundary |
| Indexing or pipeline stages | `AGENTS.md` §3.2 → `engine/tempo_engine/pipeline.py` → the one `stages/*.py` you need → `engine/tests/test_pipeline_pure.py` | you know the stage's cache deps |
| Deploy or debug infrastructure | `docs/production.md`, but read `known-issues.md` first | you know which steps are aspirational |

## The three components

### Sidecar (`service/`) — local, no ML

| File | Owns | Lines |
|---|---|---|
| `tempo_service/app.py` | All 10 routes, FastAPI wiring, lifespan (proxy, prober, tunnel) | 432 |
| `tempo_service/proxy.py` | The handoff: library hit, or upload → index → poll → thumbs | 188 |
| `tempo_service/registry.py` | Footage registry, the diff, the three reopen guards | 202 |
| `tempo_service/jobs.py` | Single-worker queue, job state machine, cancel | 160 |
| `tempo_service/tunnel.py` | `brev port-forward` supervisor | 101 |
| `tempo_service/entitlements.py` | Plan/footage/duration quotas at `/sync` (D14) | 43 |
| `tempo_service/config.py` | Every `TEMPO_*` knob and its default | 68 |
| `tempo_service/schemas.py` | Pydantic request/response models | 96 |
| `tempo_service/backends/base.py` | Provider ABC and the error codes | 58 |
| `tempo_service/backends/http_backend.py` | The only provider: engine HTTP client | 90 |
| `tempo_service/fingerprint.py` | `content_id`, duplicated in the engine on purpose | 19 |

**The seam worth testing at: `HttpBackend`.** Every engine interaction crosses it.
`service/tests/test_backends.py` (364 lines) drives a real local server and
asserts the error mapping: ASLEEP, OFFSET_MISMATCH, 401 to UNREACHABLE, TIMEOUT,
thumb cache. That is the highest-value test file in the repo.

### Engine (`engine/`) — GPU, owns the pipeline and scoring

| File | Owns | Lines |
|---|---|---|
| `tempo_engine/search.py` | The §3.5 fusion. Pure: matrices in, results out, no I/O | 190 |
| `tempo_engine/corpus.py` | Merged corpus, FAISS indexes, BM25, Gram stats | 86 |
| `tempo_engine/app.py` | The 9 `/v1` routes, bearer auth, lifespan | 238 |
| `tempo_engine/library.py` | Content-addressed store, resumable uploads, `thumbs.tar` | 149 |
| `tempo_engine/jobs.py` | Single GPU worker, durable envelopes, restart recovery | 161 |
| `tempo_engine/config.py` | `EngineSettings` and `config_signature()` | 141 |
| `tempo_engine/models.py` | Lazy locked singletons, GPU/CPU profile | 155 |
| `tempo_engine/pipeline.py` | `STAGES` and `build()` | 101 |
| `tempo_engine/cache.py` | Per-stage pickle cache | 53 |
| `tempo_engine/index.py` | `TempoIndex` save/load, display thumbs | 72 |
| `tempo_engine/textproc.py` | Tokenizer, `clean_entities`, windows, query entities | 111 |
| `tempo_engine/stages/*.py` | One module per stage; see the table below | 20–86 each |

**The seam worth testing at: `search.rank` over a prebuilt `Corpus`.** It is pure,
so `engine/tests/test_search.py` can drive it with synthetic matrices and pin
exact scores. That is why §3.5 is a formula and not a service.

Stage modules, in pipeline order:

| Stage | Module | Model source |
|---|---|---|
| `shots` | `stages/shots.py` | none (AdaptiveDetector) |
| `visual` | `stages/visual.py` | `models.get_siglip` |
| `transcribe` | `stages/speech.py` | `models.get_whisper` |
| `ocr` | `stages/ocr.py` | `models.get_easyocr` |
| `captions` | `stages/captions.py` | `models.get_florence` |
| `text` | `stages/text.py` | NER, emotion, bge |
| `index` | `index.py` (not `stages/`) | PIL only |

### Panel (`panel/`) — docked in AE

| File | Owns | Lines |
|---|---|---|
| `host/host.jsx` | Every AE project access. ES3. All five globals | 147 |
| `www/panel.js` | Store, six render functions, polling, evalScript bridge | 440 |
| `www/api.js` | The only module that talks to the sidecar | 64 |
| `www/panel.css` | All styling, including the theme variables | 152 |
| `www/index.html` | Static shell; 49 lines | 49 |
| `CSXS/manifest.xml` | Host id, version range, script load order | 48 |
| `CSXS/CSInterface.js` | Vendored, do not edit | 1203 |
| `host/json2.js` | Vendored, do not edit | 425 |

**The seam worth testing at: `GET /host/{name}.jsx` plus `ensureHost()`.** This is
the panel fetching script text and `evalScript`ing it into the AE ExtendScript
context. It is unauthenticated and unverified by design, it works only from a
source checkout, and it has **no test**. Anything you change in `host.jsx` is
reachable through it.

## The pipeline spine

Read this to know what breaks what.

```
AE import
  → host.jsx tempoListFootage()      [path,size,mtime,item_id,fps]
  → panel.js → api.js POST /sync
  → registry.diff()                  [the three reopen guards live here]
  → jobs.enqueue()                   [one active job per footage]
  → proxy._handoff()
      ├─ library hit?  content_id already indexed → done, reused=true
      └─ upload → engine POST /v1/index → GET /v1/jobs/{id} → thumbs.tar
  → engine jobs worker → pipeline.build() → 7 stages, each cached
  → search.py fusion → /v1/search → sidecar proxy → panel render
```

Dependency direction is strict: **the engine never sees a local path.** If you
find yourself wanting to send one, you are about to break §3.1.

## Hot files

By commit touches across the last 30 commits. If a ticket lands here, the blast
radius is wider than the file size suggests.

| File | Touches | Note |
|---|---|---|
| `panel/www/panel.js` | 7 | most-changed live file; the store and every renderer |
| `panel/www/index.html` | 7 | changes with panel.js, keep them in step |
| `service/tempo_service/config.py` | 4 | every knob and default |
| `service/tempo_service/app.py` | 4 | all routes |
| `service/tests/test_backends.py` | 4 | the HttpBackend seam |
| `service/tempo_service/proxy.py` | 3 | the handoff state machine |
| `service/tempo_service/schemas.py` | 3 | every response shape |

`modal_backend/` was the hottest file in history and is deleted. If you see it in
a `git log`, you are reading pre-D15 history.

## Dead directories on disk

Not code. Untracked, and a session that greps the tree will land in them.

| Path | What it is | Why it is confusing |
|---|---|---|
| `service/build/` | 13-file stale copy of the sidecar package from a `pip install ./service` | Contains `tempo_service/app.py` at an older revision. Grep for `tempo_service` and this matches. Not gitignored. |
| `auth/` | One file, `auth/.env`, holding Better Auth and Postgres values for the system D12 deleted | Gitignored, so no secret risk. Looks like live auth config. Not gitignored as a *directory*. |
| `colab/` | `tempo_shim.py`, 269 lines, the D9/D10 Colab shim | Gitignored. Mentions ngrok, Drive, COLAB_URL. All superseded by D15. |
| `tempo_pipeline_v4.ipynb` | The frozen behavioral reference | Untracked and **not** gitignored (only `v3` is). Never import it; the engine ports it. |
| `.pytest_cache/` | Test cache | Gitignored. Its `lastfailed` names tests that no longer exist. Ignore it. |

## When you are about to break a pipeline

Four rules that protect the scoring and indexing contracts. All four are enforced
by tests, so a violation is a red gate rather than a silent change.

1. **Touching `config.py` weights or `zscore_cap` does not fail any test.** The
   golden tests carry their own copy of the weights. If you change a weight, you
   must change `AGENTS.md` §3.5 and the golden constants in the same change, by
   hand, because nothing catches a half-done weight change.
2. **`signature` decides whether a library index is `ready` or `stale`.** If you
   change anything that alters index content and it is not in `config_signature()`,
   existing indexes stay `ready` and serve stale data. Two known parameters are
   currently missing from it: `caption_max_new_tokens` and `caption_num_beams`.
3. **The FAISS candidate path maps `I[]` back to shot rows.** A previous version
   assigned rank-sorted scores to row `i` and scrambled every ranking. Never index
   by rank.
4. **Queues are single-worker on both sides.** Adding concurrency to either side
   breaks the stage cache, which assumes one job owns `library/<cid>/` at a time.