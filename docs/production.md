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
$env:PYTHONPATH = "service;engine"
python -m pytest service/tests engine/tests -q   # contracts, handoff, golden, parity
python -m ruff check service engine
npx eslint panel/host/host.jsx panel/host/ae_smoke.jsx
node --check panel/www/panel.js; node --check panel/www/api.js
```

## 2. Database (Supabase, free, app tables only)

1. Create project → Settings → Database → copy the connection string.
2. Apply app tables: `psql "$DATABASE_URL" -f supabase/licenses.sql`.
3. Keep the project touched weekly (free tier pauses after 1 week idle).

## 3. Sidecar service

The sidecar is light (fastapi + pydantic only). It reaches the engine one of two ways:
- **Through Brev**: set `TEMPO_BREV_INSTANCE`. The sidecar runs and supervises
  `brev port-forward` itself.
- **Directly**: set `TEMPO_BACKEND_URL`, for example to a local CPU engine.

```powershell
cd <repo>
pip install ./service
$env:PYTHONPATH = "service"
# Brev (production): the sidecar supervises `wsl brev port-forward tempo-l4-instance --port 8900:8900`
$env:TEMPO_BREV_INSTANCE = "tempo-l4-instance"
$env:TEMPO_BREV_CLI = "wsl brev"           # brev lives in WSL on Windows (Brev quickstart)
$env:TEMPO_BACKEND_TOKEN = "<TEMPO_ENGINE_TOKEN from the instance's engine/deploy/.env>"
# Offline dev instead: $env:TEMPO_BACKEND_URL = "http://127.0.0.1:8900" (local CPU engine, §4)
python -m uvicorn tempo_service.app:app --host 127.0.0.1 --port 8765
```

Checklist:
- `GET /health` shows `backend: {reachable: true, gpu: true, tunnel: "up", signature: "…"}`.
- `POST /sync` returns diff counts.
- There is no sign-in step: every route is public on localhost (identity removed).
- WSL2 forwards its localhost ports to Windows by default. If `tunnel` stays
  `starting`, check `wsl brev ls` and the sidecar log (`brev:` lines).

## 4. Engine on Brev (L4)

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

## 5. Panel install (per machine)

```powershell
Copy-Item -Recurse -Force .\panel "$env:APPDATA\Adobe\CEP\extensions\Tempo"
reg add HKCU\Software\Adobe\CSXS.11 /v PlayerDebugMode /t REG_SZ /d 1 /f
# repeat for the CSXS.N matching your AE; fully quit AE first
```

AE → `Window > Extensions > Tempo`. DevTools at `http://localhost:8088`
→ inspect under Tempo. The debug box (`debug (copy-paste)`) carries
pinned boot lines (`panel=dbgN`, bridge/host/JSON probes, loader state).

## 6. End-to-end test (fresh project)

1. Import one mp4, then press `Sync now` in the panel.
   - The sync report reads `+1 ~0 -0 =0`.
   - The job shows `upload` (bytes) and then the engine stages, each with real `done/total`.
   - The footage row ends at `ready · N shots`.
2. Reuse check: re-import the same file from another folder (or open it in another
   project). The row goes straight to `ready · reused index`, with no upload and no stages.
3. Search → skeleton (≥200ms) → cards with thumbs, timecode, transcript/caption.
4. Click a card (or Insert shot) → layer trimmed `[start_s,end_s]` at playhead, viewer on
   first frame, selected, one Ctrl+Z removes all.
5. Quota: import a 2nd file on free → `403 QUOTA_EXCEEDED` inline;
   unchanged re-sync still passes; Retry/Resume recover failures.

## 7. Release (see docs/release.md for the full gate list)

Version map in one commit (`pyproject` ↔ manifest ↔ panel `?v=` +
`PANEL_VERSION`) → all gates green → smoke on
oldest+newest AE → `packaging\build-windows.ps1` + `zxp-sign.ps1` →
beta channel → 48h Sentry-quiet → stable. Repackage ZXP ≥60 days before
cert expiry (expired cert = silently dead panel).

## Troubleshooting (all observed in testing)

| Symptom | Cause | Fix |
|---|---|---|
| `tunnel: down`, `BACKEND_UNREACHABLE` | Instance stopped, brev CLI logged out, or WSL not running | `wsl brev ls` → `brev start tempo-l4-instance`; the sidecar reconnects on its own (backoff) |
| `BACKEND_ASLEEP` on search | Engine restarting, or query models still warming (`/v1/health` `query_models: loading`) | Wait; search resumes once `ready` |
| `upload rejected: CONTENT_MISMATCH` | File changed while uploading | Let the sync confirm the new size/mtime, then Retry |
| `SOURCE_MISSING` | Raw purged and a source stage must rerun (engine signature change) | Retry — the sidecar uploads again automatically |
| `prefetch --verify` fails on the instance | CUDA/driver or pinned-stack mismatch | Read the traceback via `brev exec tempo-l4-instance "cd ~/workspace/tempo-src/engine/deploy && docker compose logs --tail 200"` |
| `sync +0`, `evalScript raw len=0` | CEP skipped ScriptPath eval | Loader self-heals (watch `loader:` lines); else reinstall + full AE quit |
| `Expected: )` running host scripts | Regex literal in ES3 | No regex in `host.jsx` (ESLint gate enforces) |
| `403 QUOTA_EXCEEDED` | Free tier: 1 footage / 7 min | Prune project or upgrade plan |
| Old UI after update | CEF cache | `?v=` bump (in map) + full AE quit |
| `MODEL_NOT_LOADED` | Query model load failed on the engine | Engine logs; rerun `prefetch --verify` |
