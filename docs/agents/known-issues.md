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
| The ES3 gate does not enable `no-undef` | `eslint.config.mjs:29-41` | The `globals` list is inert. `docs/production.md` claims a regex ban that does not exist. |
| Anchor guard `hit.sum() == n` untested | `search.py:177` | Only the `== 0` side is covered. |
| `.npz` L2-norm invariant unasserted | `index.py:21-24` | §3.6 claims V, D, C are L2-normed; nothing pins it. |

The nine unpinned constants: port `8765` (`service/config.py:18`,
`panel/api.js:7`); sync poll `2.0` and job poll `0.5` (`config.py:30-31`,
`panel.js:10-11`, which admits in a comment that they are kept in step by hand);
frame rate `25.0` (`schemas.py:22`, `panel.js:22`, `host.jsx:37,131`);
`1920x1080` and `60.0` second comp fallback (`host.jsx:131,133`); `top_k` `8`
(`panel.js:260,388`, `app.py:405`).

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
| `service/build/` | A 13-file stale copy of the sidecar package. Grepping `tempo_service` matches it. Not gitignored. |
| `auth/` | Holds `auth/.env` with Better Auth and Postgres values for the system D12 deleted. Gitignored, so no secret risk, but it reads as live config. |
| `colab/` | `tempo_shim.py`, 269 lines. The D9/D10 shim: ngrok, Drive, `COLAB_URL`. All superseded by D15. Gitignored. |
| `tempo_pipeline_v4.ipynb` | Untracked and **not** gitignored. Only `v3` is. Never import it. |
| `.pytest_cache/v/cache/lastfailed` | Names tests that no longer exist. Ignore it. |

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
- `panel.js:81-84` holds display names for the 7 engine stages, a fourth copy of
  the stage vocabulary after `docs/api.md`, `README.md`, and `/v1/health`. No test
  pins them.
- `panel.js:372-373` keeps the indexing detail **open** when a job failed, which
  `AGENTS.md` §4.4 does not mention.
- `panel.js` has six render functions and no single `render()`. `showError()`
  writes to the DOM directly, and `evalScript` and `probe` are two implementations
  of the same thing.
- `panel.css:9-11` hardcodes `--border`, `--text`, `--dim`. Only `--bg` comes from
  `appSkinInfo` (`panel.js:52`).