# Production setup + test guide (D11–D14)

Windows-only editor scope. The GPU engine runs on an NVIDIA Brev L4 instance
(billed per running hour, ADR-0008); Supabase free; local dev fully offline
(engine on CPU).

## 0. Prerequisites

- Windows 10/11, Python 3.11+, Node 20+, After Effects (note exact version
  for the smoke sign-off), Git.
- Accounts: NVIDIA Brev (org with GPU access), Supabase (one project, app tables only).
- WSL Ubuntu on Windows for the brev CLI (Brev quickstart).

## 1. Repo verify (no services running)

```powershell
cd <repo>
$env:PYTHONPATH = "service;."
python -m pytest service/tests -q        # 69 tests: golden, parity, contracts
python -m ruff check service modal_backend
npx eslint panel/host/host.jsx panel/host/ae_smoke.jsx
node --check panel/www/panel.js; node --check panel/www/api.js
```

## 2. Database (Supabase, free, app tables only)

1. Create project → Settings → Database → copy the connection string.
2. Apply app tables: `psql "$DATABASE_URL" -f supabase/licenses.sql`.
3. Keep the project touched weekly (free tier pauses after 1 week idle).

## 3. Sidecar service

```powershell
cd <repo>
pip install ./service
$env:PYTHONPATH = "service"
$env:TEMPO_BACKEND = "local"   # offline dev; "http" + TEMPO_BACKEND_URL/TOKEN for Modal
python -m uvicorn tempo_service.app:app --host 127.0.0.1 --port 8765
```

Checklist: `GET /health` → ok; `POST /sync` → diff counts; no sign-in
step — every route is public on localhost (identity removed).

## 5. Engine on Brev (L4)

**One-time setup:**
1. In the Brev console (https://brev.nvidia.com), create a VM-mode instance.
   - GPU: **L4**
   - Name: **`tempo-l4-instance`**
   - Disk: 200 GiB or more (model cache plus library)

   `brev create` flag syntax is not in the docs we verified, so the
   console is the documented path.
2. Install the brev CLI where the deploy runs. On Windows it goes in WSL
   Ubuntu, per the Brev quickstart:
   `bash -c "$(curl -fsSL https://raw.githubusercontent.com/brevdev/brev-cli/main/bin/install-latest.sh)"`.
   Then run `brev login` (or `brev login --token` headless) and `brev ls`.
3. Make sure the instance can clone the repo, for example with a deploy key
   under `~/.ssh` on the instance (`brev shell tempo-l4-instance`).

**Deploy / update (idempotent):**

```bash
TEMPO_REPO_URL=git@github.com:<org>/tempo.git ./engine/deploy/brev-deploy.sh
```

The script runs through `brev exec` and does the following:
1. Pulls `TEMPO_REPO_REF` (default `main`) into `~/workspace/tempo-src`.
2. Creates `engine/deploy/.env` from `.env.example` on the first run, with a
   random `TEMPO_ENGINE_TOKEN`. Copy that token to the sidecar as
   `TEMPO_BACKEND_TOKEN`.
3. Runs `docker compose up -d --build` with the GPU reservation and
   `restart: unless-stopped`. The API is published on the instance's
   `127.0.0.1:8900` only.
4. Runs `prefetch --verify`, which downloads every model into
   `/home/ubuntu/workspace/tempo/hf`, loads the query models on the GPU, and
   runs a tiny inference. This is the first-deploy check of the pinned
   CUDA 12.6 / cuDNN 9 stack.
5. Prints `/v1/health`, which must show `"gpu": true` and
   `"query_models": "ready"`.

**Data on the instance (`/home/ubuntu/workspace/tempo`):**
- `hf/`: model cache
- `library/<content_id>/`: stage cache, frames, thumbs, index
- `raw/`: purged after index
- `jobs/`

The workspace survives `brev stop` and `brev start`. `brev delete` erases
it; the library is then rebuilt from uploads.

**Offline dev (no GPU):** run the same engine on CPU with the notebook's CPU
model defaults:

```powershell
pip install "./engine[ml]"        # torch CPU wheels are fine locally
$env:TEMPO_ENGINE_TOKEN = "dev-token"; $env:TEMPO_ENGINE_DATA_ROOT = ".\engine-data"
python -m tempo_engine.prefetch   # once
python -m tempo_engine.app        # http://127.0.0.1:8900
```

**GPU trial:**
1. Index a 2-minute clip.
2. Record wall time per footage minute and peak VRAM
   (`brev exec tempo-l4-instance "nvidia-smi"`).
3. `docker compose restart` mid-index. The job must resume from the stage
   cache: finished stages are logged as `cache hit`.

## 6. Storage step-up (only when leaving manual copy)

Day-zero needs nothing (Modal Volumes are in-stack). For presigned uploads:

1. B2 bucket `tempo`, application key (read/write that bucket only).
2. Sidecar env: `TEMPO_STORAGE_PROVIDER=s3`,
   `TEMPO_STORAGE_ENDPOINT=https://s3.<region>.backblazeb2.com`,
   `TEMPO_STORAGE_BUCKET=tempo`, `TEMPO_STORAGE_KEY/Secret` (env only).
3. Sync a new footage → `upload` stage shows real bytes; after `done`,
   the raw key is purged (`storage_retention=delete`, locked).
4. R2 later = endpoint + credentials swap, no code changes.

## 7. Panel install (per machine)

```powershell
Copy-Item -Recurse -Force .\panel "$env:APPDATA\Adobe\CEP\extensions\Tempo"
reg add HKCU\Software\Adobe\CSXS.11 /v PlayerDebugMode /t REG_SZ /d 1 /f
# repeat for the CSXS.N matching your AE; fully quit AE first
```

AE → `Window > Extensions > Tempo`. DevTools at `http://localhost:8088`
→ inspect under Tempo. The debug box (`debug (copy-paste)`) carries
pinned boot lines (`panel=dbgN`, bridge/host/JSON probes, loader state).

## 8. End-to-end test (fresh project)

1. Import 1 mp4 → panel `Sync now` → `+1 ~0 -0 =0`, job runs 10 stages
   with real `done/total` → footage row `ready · N shots`.
2. Search → skeleton (≥200ms) → cards with thumbs, timecode, transcript/caption.
3. Click a card (or Insert shot) → layer trimmed `[start_s,end_s]` at playhead, viewer on
   first frame, selected, one Ctrl+Z removes all.
4. Quota: import a 2nd file on free → `403 QUOTA_EXCEEDED` inline;
   unchanged re-sync still passes; Retry/Resume recover failures.

## 9. Release (see docs/release.md for the full gate list)

Version map in one commit (`pyproject` ↔ manifest ↔ panel `?v=` +
`PANEL_VERSION`) → all gates green → smoke on
oldest+newest AE → `packaging\build-windows.ps1` + `zxp-sign.ps1` →
beta channel → 48h Sentry-quiet → stable. Repackage ZXP ≥60 days before
cert expiry (expired cert = silently dead panel).

## Troubleshooting (all observed in testing)

| `modal stage needs X ... (import failed: ...)` | Image missing a dep or system lib | Suffix names the root cause (often a `.so` — add the apt lib to `modal_app.py`); redeploy |
| `did not match any variant ... at line N` | Version gap: pinned tokenizers 0.19.1 rejects current `tokenizer.json` (proven: 0.23.2 parses + encodes it; file byte-valid) | Fixed in code (`use_fast=False`, `99a07ec`); purge-on-serde remains for genuine corruption — just Retry |
| Symptom | Cause | Fix |
|---|---|---|
| `sync +0`, `evalScript raw len=0` | CEP skipped ScriptPath eval | Loader self-heals (watch `loader:` lines); else reinstall + full AE quit |
| `Expected: )` running host scripts | Regex literal in ES3 | No regex in `host.jsx` (ESLint gate enforces) |
| `footage not on Drive/storage` | Bytes never uploaded | Copy to the exact key, or configure storage + Retry |
| `403 QUOTA_EXCEEDED` | Free tier: 1 footage / 7 min | Prune project or upgrade plan |
| `BACKEND_ASLEEP/TIMEOUT` | Workers cold/slow | Wait + poll; warm pool before launch pricing |
| Old UI after update | CEF cache | `?v=` bump (in map) + full AE quit |
| `MODEL_NOT_LOADED` 503 | No cached text model | Local path needs weights; backend path needs warm pool |
