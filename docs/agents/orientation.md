# Orientation

Read your section, not the codebase. This file maps every component to its files,
names the seams worth testing at, and lists the dead directories on disk that are
not code.

Line counts were re-measured on 2026-10-05. They are there to size a read, not as
a contract; `git log --oneline -5 -- <path>` is the authority for "is this current".

## Read order by task type

| Your task | Read, in this order | Stop when |
|---|---|---|
| Anything at all | `AGENTS.md` §0, then this file, then `known-issues.md` | you can name the files you'll touch |
| Touch `search.py` or scoring | `AGENTS.md` §3.5 → `engine/tempo_engine/search.py` → `corpus.py` → `engine/tests/test_search.py` | you can recite the six components and their weights |
| Change an endpoint | `docs/api.md` (sidecar) or `docs/engine-api.md` (engine) → the `app.py` route → `schemas.py` → the matching contract test | you know the response shape and the auth requirement |
| Change sync or registry behavior | `AGENTS.md` §3.3 → `registry.py` → `service/tests/test_registry.py` and `test_sync.py` | you know which of the three reopen guards you are touching |
| Touch the panel | `AGENTS.md` §4 and §6 → `panel/www/api.js` → `panel/www/panel.js` → `panel/host/host.jsx` | you know which side of the evalScript bridge you are on |
| Touch `host.jsx` | `AGENTS.md` §4.2 and §4.3 → `panel/host/host.jsx` (157 lines, read all of it) → `eslint.config.mjs` | you can state the undo-group boundary |
| Indexing or pipeline stages | `AGENTS.md` §3.2 → `engine/tempo_engine/pipeline.py` → the one `stages/*.py` you need → `engine/tests/test_pipeline_pure.py` | you know the stage's cache deps |
| Deploy or debug infrastructure | `docs/production.md`, but read `known-issues.md` first | you know which steps are aspirational |

## The three components

### Sidecar (`service/`) — local, no ML

| File | Owns | Lines |
|---|---|---|
| `tempo_service/app.py` | All 10 routes, FastAPI wiring, lifespan (proxy, prober, tunnel) | 507 |
| `tempo_service/proxy.py` | The handoff: library hit, or upload → index → poll → thumbs | 260 |
| `tempo_service/registry.py` | Footage registry, the diff, the three reopen guards, the write lock | 281 |
| `tempo_service/jobs.py` | Single-worker queue, job state machine, cancel | 196 |
| `tempo_service/tunnel.py` | `brev port-forward` supervisor | 118 |
| `tempo_service/entitlements.py` | Plan/footage/duration quotas at `/sync` (D14) | 51 |
| `tempo_service/config.py` | Every `TEMPO_*` knob and its default | 85 |
| `tempo_service/schemas.py` | Pydantic request/response models | 132 |
| `tempo_service/backends/base.py` | Provider ABC and the error codes | 77 |
| `tempo_service/backends/http_backend.py` | The only provider: engine HTTP client | 110 |
| `tempo_service/fingerprint.py` | `content_id`, duplicated in the engine on purpose | 24 |

**The seam worth testing at: `HttpBackend`.** Every engine interaction crosses it.
`service/tests/test_backends.py` (552 lines) drives a real local server and
asserts the error mapping: ASLEEP, OFFSET_MISMATCH, 401 to UNREACHABLE, TIMEOUT,
thumb cache. That is the highest-value test file in the repo.

### Engine (`engine/`) — GPU, owns the pipeline and scoring

| File | Owns | Lines |
|---|---|---|
| `tempo_engine/search.py` | The §3.5 fusion. Pure: matrices in, results out, no I/O | 225 |
| `tempo_engine/corpus.py` | Merged corpus, FAISS indexes, BM25, Gram stats | 106 |
| `tempo_engine/app.py` | The 9 `/v1` routes, bearer auth, lifespan | 292 |
| `tempo_engine/library.py` | Content-addressed store, resumable uploads, `thumbs.tar` | 179 |
| `tempo_engine/jobs.py` | Single GPU worker, durable envelopes, restart recovery | 182 |
| `tempo_engine/config.py` | `EngineSettings` and `config_signature()` | 173 |
| `tempo_engine/models.py` | Lazy locked singletons, GPU/CPU profile | 213 |
| `tempo_engine/pipeline.py` | `STAGES` and `build()` | 123 |
| `tempo_engine/cache.py` | Per-stage pickle cache | 65 |
| `tempo_engine/atomic.py` | tmp + `replace` for every durable write. One per package, see `AGENTS.md` §8 | 41 |
| `tempo_engine/index.py` | `TempoIndex` save/load, display thumbs | 91 |
| `tempo_engine/textproc.py` | Tokenizer, `clean_entities`, windows, query entities | 133 |
| `tempo_engine/prefetch.py` | CLI that snapshots HF and EasyOCR weights to the data volume | 66 |
| `tempo_engine/stages/*.py` | One module per stage; see the table below | 25–105 each |

**The seam worth testing at: `search.rank` over a prebuilt `Corpus`.** It is pure,
so `engine/tests/test_search.py` can drive it with synthetic matrices and pin
exact scores. That is why §3.5 is a formula and not a service.

Stage modules, in pipeline order:

| Stage | Module | Model source |
|---|---|---|
| `shots` | `stages/shots.py` | none (AdaptiveDetector) |
| `visual` | `stages/visual.py` | `models.get_siglip` |
| `transcribe` | `stages/speech.py` | loaded inline in the stage, no `models.get_*` |
| `ocr` | `stages/ocr.py` | loaded inline via `stages/ocr.py::_reader` |
| `captions` | `stages/captions.py` | loaded inline in the stage, no `models.get_*` |
| `text` | `stages/text.py` | NER, emotion, bge |
| `index` | `index.py` (not `stages/`) | PIL only |

Only the three query models go through the `models.py` singleton registry
(`get_siglip`, `get_text_embedder`, `get_ner`). Whisper, EasyOCR and Florence-2
load inside their stage modules and free themselves, which is why
`models.release()` has no caller. See `known-issues.md`.

### Panel (`panel/`) — docked in AE

| File | Owns | Lines |
|---|---|---|
| `host/host.jsx` | Every AE project access. ES3. All five globals | 157 |
| `www/panel.js` | Store, 9 `render*` functions plus a `render()` dispatcher, polling, evalScript bridge | 1015 |
| `www/api.js` | The only module that talks to the sidecar | 70 |
| `www/panel.css` | All styling, including both themes | 584 |
| `www/index.html` | Static shell | 129 |
| `CSXS/manifest.xml` | Host id, version range, script load order | 48 |
| `CSXS/CSInterface.js` | Vendored, do not edit | 1292 |
| `host/json2.js` | Vendored, do not edit | 531 |

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

Commit touches across the last 30 commits. If a ticket lands here, the blast
radius is wider than the file size suggests. Docs dominate the count, so the
live-code rows follow the test file that pins them.

| File | Touches | Note |
|---|---|---|
| `service/tests/test_contracts.py` | 21 | the panel and markup contract, run under the **service** CI job |

`docs/agents/orientation.md`'s own tables are the map for the rest. The panel
files above are hot because of design work, not because the sidecar needs it.
| `panel/www/panel.js` | 16 | most-changed source file; the store and every renderer |
| `panel/www/panel.css` | 16 | both palettes and every token |
| `panel/www/index.html` | 16 | changes with panel.js, keep them in step |
| `docs/design/preview.html` | 9 | the markup the contract test pins |
| `docs/design/preview-harness.js` | 5 | stubs only, never shipped |

No `service/tempo_service/` source file appears in the last 30 commits. The
sidecar is stable, which is a reason to trust its current shape rather than a
reason it needs work.

`modal_backend/` was the hottest file in history and is deleted. If you see it in
a `git log`, you are reading pre-D15 history.

## Dead directories on disk

Not code. Untracked, and a session that greps the tree will land in them.

| Path | What it is | Why it is confusing |
|---|---|---|
| `service/build/` | 13-file stale copy of the sidecar package from a `pip install ./service` | Contains `tempo_service/app.py` at an older revision. Grep for `tempo_service` and this matches. Gitignored. |
| `engine/build/` | 22-file stale copy of the engine package, same origin | Same trap as above, for `tempo_engine`. Not in this table's previous revision. Gitignored. |
| `service/tempo_service/indexer/` | Empty. `__pycache__` only, from the deleted pre-D15 pipeline | No `.py` file remains. Grep for `indexer` finds six stale `.pyc` names. |
| `service/tempo_service/storage/` | Empty. `__pycache__` only, from the deleted storage providers (D13) | Same. Mentions `s3`. |
| `auth/` | One file, `auth/.env`, holding Better Auth and Postgres values for the system D12 deleted | Gitignored, so no secret risk. Looks like live auth config. |
| `colab/` | `tempo_shim.py`, 269 lines, the D9/D10 Colab shim | Gitignored. Mentions ngrok, Drive, COLAB_URL. All superseded by D15. |
| `tempo_pipeline_v4.ipynb` | The frozen behavioral reference | Untracked **and** gitignored. Never import it; the engine ports it. |
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