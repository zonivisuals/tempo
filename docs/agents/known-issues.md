# Known issues

Verified divergences between `AGENTS.md` and the code, plus hazards that cost
sessions time. Every entry was checked against the files on disk. When you fix one,
delete the entry and note it in `docs/decisions/README.md` if it changes a spec.

Read this before you act on a spec line that looks surprising.

## Fixed in the last pass

These were wrong in `AGENTS.md` and are now corrected. Listed so you know what
changed and can check the reasoning.

| Was wrong | Now says | Verified against |
|---|---|---|
| Registry maps to `{fingerprint, content_id, format_version, stats}` | Entry is flat; no nested `fingerprint` or `stats` | `registry.py:180-192` |
| `host.jsx` exposes "exactly three global functions" | Three **contract** entry points, plus two internal helpers that are technically global because ExtendScript has no module scope | `host.jsx:16,55,66,90,106` |
| Route table omitted `GET /host/{name}.jsx` | Route documented, with its security shape and its source-checkout-only constraint | `app.py:252`, route added to §3.4 |
| EasyOCR weights live under `hf/` | They live in `<data_root>/easyocr/`, a sibling of `hf/` | `stages/ocr.py:26,39` |
| `thumbs.tar` absent from the artifacts tree | Added | `library.py:32,168` |
| Both sides accept an optional config file | Engine is environment-only | `config.py:41-45` |
| F1: removal marks footage "upload cancelled" | Not implemented. `jobs.cancel()` is reachable only via `POST /jobs/{id}/cancel` | `app.py:331` is the only call site |
| `prune_stale` listed as live config | Dead knob, no caller | `registry.py:225` defined, never called |
| §2.2 omitted `entitlements.py` and the CI files | Added | `service/tempo_service/entitlements.py` |
| §9: panel payload "must satisfy the same schema fixture" | Only a substring check against `panel.js` source text | `test_contracts.py:85-89` |
| §6 radius rule had no exception | The 7px status dot is a documented exception | `panel.css:34` |

## Open: spec disagrees with code

### The declared CEP floor is not the real one

`panel/CSXS/manifest.xml:20` declares `<RequiredRuntime Name="CSXS" Version="9.0" />`.
Per the CEP 12 Cookbook's CEF table that is Chromium 61 (CEF 3 branch 3163).
Two things in the shipped panel need newer than that:

- **flexbox `gap`** — Chromium 84. Used in `panel.css` since the current layout
  landed, and relied on throughout the ADR-0011 rewrite.
- **`prefers-reduced-motion`** — Chromium 74. Used by the ADR-0011 motion
  budget; it silently no-ops below that.

**Consequence:** the manifest advertises CC 2019 / 2020 (AEFT 16–17, CEP 9) but
the panel has never worked there. Either narrow `<Host Name="AEFT">` to the
versions actually on `docs/ae-smoke.md`, or replace `gap` with margins and drop
the media query. Until one of those happens, treat CC 2019+ as untested rather
than supported — the wide-compat claim in `AGENTS.md` is a target, not a fact.

### Panel errors are not the server's errors

`panel.js` reads `res.body.error.{code,message}` for search only. `POST /sync`,
`POST /jobs/{id}/retry` and `POST /footage/{key}/retry` replace both with a
panel-synthesized code and `status N`, so a quota denial renders
`SYNC_FAILED · status 403` while the real message ("plan 'free' allows 3
footage; project holds 4") is discarded. `GET /footage` has no `else` branch at
all. Thumbnail failures are invisible: the URL goes straight into `<img src>`,
and `app.py:462-464` maps a fully unreachable engine to `404 unknown thumbnail`,
so a dead engine renders as broken images rather than an error.

**Consequence:** the inline error row is laid out for the honest version but the
data is not honest yet. Tracked in `docs/design/panel-ui.md` §6; needs
`docs/api.md` updated in the same change (`INTERNAL`, sidecar `NOT_FOUND`, the
422 `detail` envelope and the `starting` tunnel state are all undocumented).

### The result card shows no timecode in the grid view

`AGENTS.md` §5 F2 lists the card's contents as "keyframe thumbnail, footage name,
timecode range (comp-fps timecode, from project fps), duration, transcript
snippet, caption". `renderResults` gates the timecode to list view only
(`panel.js:526`), so a grid card carries no timecode at all.

**Consequence:** F2's timecode requirement is met in one of the two views and the
default view is the other one. This predates ADR-0014, which re-derived the grid
body and did not change it: the grid has no width for a `00:00:01:12 –
00:00:04:18` pair beside a description, and the duration is the fact worth its
11px. Whether the timecode belongs as a third metadata line is a separate call
about what a grid cell carries.

### Config weights are not pinned by any test

`engine/tests/test_search.py:14-15` hardcodes its own `WEIGHTS` and `CAP = 3.0`
instead of importing `config.weights(settings)` and `settings.zscore_cap`.

**Consequence:** changing `w_*` or `zscore_cap` in `config.py` breaks no test.
`AGENTS.md` §0.5 and §11 both require a weight change to update spec, config, and
tests together, and nothing enforces the config half. A weight change is a
three-file edit done by hand.

### Two indexing parameters are missing from `config_signature()`

`caption_max_new_tokens` and `caption_num_beams` (`config.py:92-93`) change caption
text, and therefore the `C` matrix, but appear in neither `config_signature()`
(`config.py:155-166`) nor the captions stage deps (`pipeline.py:47-48`).

**Consequence:** changing either does not mark an existing library index stale and
does not rerun the `captions` stage. Existing indexes serve stale captions
indefinitely.

### `qv`'s prompt template is a module constant, not config

`models.py:34-35` holds `SIGLIP_TEXT_TEMPLATE = "this is a photo of {}."` and
`SIGLIP_MAX_LENGTH = 64`. Both change the `qv` input to the fusion. The symmetric
bge query prompt **is** in config (`config.py:68`).

**Consequence:** changing the SigLIP template does not mark indexes stale, and
`AGENTS.md` §3.5 describes it as part of the pinned contract while it lives in
code outside config and outside the signature.

### Stage 7 (`index`) is not cache-backed

`AGENTS.md` §3.2 says "Each stage is pickled under a hash of its inputs." Stages 1
through 6 are. `index` is not: `pipeline.py:117-120` calls `write_thumbs` and
`save` directly. Harmless in practice, since re-running it is cheap, but the spec
sentence is not true as written.

### Model load/unload is only partly logged

`AGENTS.md` §7.3 requires logging load and unload. `models.py:99,105` and
`captions.py:50,70` do. EasyOCR (`stages/ocr.py:36`) and Whisper
(`stages/speech.py:39`) do not.

### Whisper model names are hardcoded in stage logic

`stages/speech.py:21` `TURBO_FALLBACK = {True: "large-v3", False: "medium"}`.
`AGENTS.md` §8 prohibits model names in logic. The `config.py` override path still
works; this is a fallback map that bypasses it.

### Host.jsx globals reachable from the panel

`AGENTS.md` §4.2 now names `tempoFindFootage` and `tempoInsertOrFocusInner` as
internal. They are still global and still callable from `evalScript`; ExtendScript
has no module scope. If you add a helper, do not assume it is private.

## Open: untested or unguarded

| Item | Where | Why it matters |
|---|---|---|
| `GET /host/{name}.jsx` has **no test** | `app.py:252` | It serves script text that the panel `evalScript`s into AE. Unauthenticated, no integrity check. |
| Panel insert payload uses substring checks, not a schema fixture | `test_contracts.py:85-89` | The panel and sidecar can drift apart and the test still passes. |
| `POST /jobs/{id}/cancel` has no `api.js` method | `app.py:325` | A live server feature plus a documented route the panel cannot reach. |
| Nine cross-runtime constants have no cross-check test | see below | `AGENTS.md` §7.3 and §8 require either derivation or a pinning test. |
| Panel card layout is pinned as CSS text, never as computed geometry | `test_contracts.py` (the `#results.grid .body` tests) | The `grid-row: 1 / -1` span rendered 9px off while every declaration assertion passed. Same bargain §9 strikes for AE: no browser in CI, so the check is a headless measurement and the finding goes in the test docstring. |
| The ES3 gate does not enable `no-undef` | `eslint.config.mjs:29-41` | The `globals` list is inert. `docs/production.md` claims a regex ban that does not exist. |
| Anchor guard `hit.sum() == n` untested | `search.py:177` | Only the `== 0` side is covered. |
| `.npz` L2-norm invariant unasserted | `index.py:21-24` | §3.6 claims V, D, C are L2-normed; nothing pins it. |

The nine unpinned constants: port `8765` (`service/config.py:18`,
`panel/api.js:7`); sync poll `2.0` and job poll `0.5` (`config.py:30-31`,
`panel.js:10-11`, which admits in a comment that they are kept in step by hand);
frame rate `25.0` (`schemas.py:22`, `panel.js`, `host.jsx:37,131`);
`1920x1080` and `60.0` second comp fallback (`host.jsx:131,133`).
`top_k` is no longer on this list — ADR-0011 moved it to 9 and
`test_contracts.py::test_panel_top_k_matches_service` pins it.

## Open: docs describing things that do not exist

`docs/production.md` and `docs/release.md` are the weakest docs in the repo. They
describe systems that were never built or have been deleted.

| Claim | Reality |
|---|---|
| `production.md:144`: import a **2nd** file on free hits `403` | Free allows 3 (`c9960a1`). It is the 4th. The troubleshooting-table row was corrected in that commit; this line was not. |
| `production.md:130-131`: panel debug box with boot lines, `loader:` lines | No such element in `index.html`; `ensureHost()` logs nothing. The box was removed outright in `60884a4`, so the doc now describes a UI that cannot exist. |
| `production.md`: Supabase setup, `psql -f supabase/licenses.sql` | No code reads `licenses`. `entitlements.py` says "once billing lands". |
| `production.md`: 48h Sentry-quiet gate | Sentry appears nowhere in the repo. |
| `production.md`: no regex in `host.jsx`, "ESLint gate enforces" | No such ESLint rule. |
| `release.md`: Velopack setup, beta channel, Stripe webhooks | Not in the repo. `packaging/` has two PowerShell scripts. |
| `release.md` version map | Manifest says `0.1.1`, both `pyproject.toml` say `0.1.0`, panel says `0.4.0`. The map requires one bump commit. |

`docs/api.md` is accurate and complete apart from `INTERNAL` and the sidecar
`NOT_FOUND`. Trust it over the others.

## Hazards on disk

| Path | Why it costs time |
|---|---|
| `service/build/` | A 13-file stale copy of the sidecar package. Grepping `tempo_service` matches it. Gitignored (`.gitignore:10`, `build/`) and untracked. |
| `auth/` | Holds `auth/.env` with Better Auth and Postgres values for the system D12 deleted. Gitignored, so no secret risk, but it reads as live config. |
| `colab/` | `tempo_shim.py`, 269 lines. The D9/D10 shim: ngrok, Drive, `COLAB_URL`. All superseded by D15. Gitignored. |
| `tempo_pipeline_v4.ipynb` | Untracked **and** gitignored (`.gitignore`, last entry). Never import it. |
| `.pytest_cache/v/cache/lastfailed` | Names tests that no longer exist. Ignore it. |

## Security findings not yet fixed

Verified by a full-repo and full-history scan. **None of these is a committed
secret** — `git log --all -p` plus every blob on every ref is clean of private
keys, cloud/GitHub/Slack/OpenAI/Anthropic/Google/Stripe tokens, JWTs and
credentials. These are the real ones.

### S1 The sidecar treats an unauthenticated request body as trusted local paths — HIGH

`POST /sync` accepts `footages[].path` with no validation (`schemas.py`,
`FootageItem.path: str`). The only check anywhere downstream is
`os.path.isfile` (`proxy.py`), after which the file is read and streamed to the
engine over the Brev tunnel. Any local process can therefore make the sidecar
read arbitrary files and ship them off-box, plus probe existence via the job
error string and confirm byte-identity via `content_id` in `GET /footage`.

Cross-origin reachable too: FastAPI parses a body sent with **no `Content-Type`**
as JSON (`fastapi/routing.py`), and that is a CORS simple request. The design
docs trust the *caller* in prose and never enforce it.

Fix shape: accept only paths the service can corroborate, or drop `path` from
the request and let the service resolve footage itself.

### S2 No `TrustedHostMiddleware`, no CORS — HIGH (as an amplifier)

`create_app()` installs no middleware at all. DNS rebinding therefore makes a
public page **same-origin** with the sidecar, so every response becomes
readable — `/footage`, `/jobs/{id}`, `/search`, `/host/host.jsx`. Verified: a
request carrying `Host: evil.example.com` is served normally.

Note the panel loads from `file://`, which is itself cross-origin, so any CORS
fix must be checked against the panel's current working path before shipping.

### S3 `pickle.load` on a host-writable volume — CRITICAL as a design, not reachable today

`engine/tempo_engine/cache.py` is the only `pickle.load` in the engine. `/data` is
a bind mount of a Brev host directory and the container runs at the same uid as
the host writer, so a poisoned `library/<cid>/stages/*.pkl` is code execution
plus both tokens from `/proc/self/environ`. No route writes `stages/`, so this
is not network-reachable — and it becomes so the moment anyone adds uid
isolation or a second container on `/data`.

Fix shape: a non-executing format (`.npz` + JSON, which `index.py` already
uses), or document `stages/` as exactly as trusted as the engine process.

### S4 Unbounded inbound buffers and query lengths — HIGH

- The engine buffers a whole upload body before the size check
  (`await request.body()`); a chunked request skips the `Content-Length`
  pre-check entirely.
- `q` has no `max_length` on either service. Measured on this repo's own
  `textproc`: ~9 s of CPU per request against a 60k-entity library, because
  entity resolution is a pure-Python n-gram scan.
- `SyncRequest.footages` has no `max_length`; `/search` and `/thumb` are
  unauthenticated and unrated, and `/thumb` misses write unbounded files into
  the cache with no eviction.

### S5 Job errors return absolute paths and tracebacks — MEDIUM

`engine/tempo_engine/jobs.py` stores `f"{exc}\n{traceback tail}"` in the job
error, which `GET /v1/jobs/{id}` and `GET /v1/library/{cid}` return. Leaks
container paths, resolved model ids and stack frames. Also reflected verbatim
into sidecar responses and logs (`proxy.py`).

### S6 `GET /v1/library/{cid}` creates directories on a read path — MEDIUM

`library.entry_dir()` `mkdir(parents=True)` runs unconditionally, and
`needs_upload` reaches it from the GET. Verified: three GETs for an unuploaded
content id created three directory trees. Unbounded inode growth on the persistent
volume, and `ready_ids` then walks them on every search.

### S7 Credential-shaped strings in history — LOW, not fixable without a shared rewrite

`packaging/build-windows.ps1` carried `://postgres:postgres@` and
`://postgres:change-me@` at commit `8d6b8d0` — default local-dev Postgres
credentials for the auth service D12 deleted. Removed from HEAD; still in
history. Scrubbing it means rewriting a commit that is on `origin/main`.

## Undocumented behavior worth knowing

Load-bearing behavior with no spec line, found during the audit:

- `app.py:274` resolves `panel/host/` by walking **two directories up out of its
  own installed package**. `GET /host/{name}.jsx` therefore only works from a
  source checkout, and would break under `pip install ./service`. Both
  `docs/production.md` and `README.md` instruct `pip install ./service`.
- `app.py:174-180` logs only the first 10 footages per sync.
- `app.py:155-161` probes the engine synchronously only when the health cache was
  never populated; `app.py:76-78` keeps the last known stage list across an
  unreachable engine.
- `panel.js` holds editorial labels for the eight engine stages plus a synthetic
  `queued` row in its `STEPS` map, a fourth copy of the stage vocabulary after
  `docs/api.md`, `README.md` and `/v1/health`. No test pins the labels, only
  that the keys match the engine's stage names.
- `panel.css` ships both a dark and a light palette; `appSkinInfo` is read only
  to decide which one applies (`panel.js` `applyTheme`, ADR-0011). A user with a
  custom AE panel colour no longer gets that colour in Tempo.
- `panel.js` `fmtTC()` falls back to 25 fps when `tempoGetActiveCompInfo()`
  returns `{ok:false}` or unparseable output, so timecodes render at the wrong
  rate with no indication that it happened.