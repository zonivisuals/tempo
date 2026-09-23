# Production setup + test guide (D11–D14)

Windows-only scope. No cards required until billing: Modal Starter ($30/mo
credits), Supabase free, Backblaze B2 free tier, local dev fully offline.

## 0. Prerequisites

- Windows 10/11, Python 3.11+, Node 20+, After Effects (note exact version
  for the smoke sign-off), Git.
- Accounts (all free, no card): Modal (`modal.com`, token via `modal setup`),
  Supabase (one project), Backblaze B2 (only when leaving manual-copy mode).
- Google/GitHub OAuth clients: only when enabling social login (else skipped).

## 1. Repo verify (no services running)

```powershell
cd <repo>
$env:PYTHONPATH = "service;."
python -m pytest service/tests -q        # 69 tests: golden, parity, contracts
python -m ruff check service modal_backend
npx eslint panel/host/host.jsx panel/host/ae_smoke.jsx
node --check panel/www/panel.js; node --check panel/www/api.js
node --check auth/server.mjs; node --check auth/auth.mjs
```

## 2. Database (Supabase, free)

1. Create project → Settings → Database → copy the **pooler** connection
   string (port 6543) into `auth/.env` as `DATABASE_URL`. If your network
   filters 6543 (test: `Test-NetConnection <host> -Port 6543`), use the
   **direct** host (`db.<ref>.supabase.co`, port 5432) instead.
2. Apply app tables: `psql "$DATABASE_URL" -f supabase/licenses.sql`
   (auth tables are CLI-managed, never hand-written).
3. Keep the project touched weekly (free tier pauses after 1 week idle).

## 3. Identity service

```powershell
cd auth
cp .env.example .env   # BETTER_AUTH_API_KEY (>=32 chars), BETTER_AUTH_URL, DATABASE_URL
pnpm install
pnpm migrate           # migrate.mjs via installed better-auth (never hand-made)
pnpm start             # 127.0.0.1:18099
```

Verify (shapes pinned in `service/tests/test_auth.py`):

```powershell
curl -s -X POST http://127.0.0.1:18099/api/auth/sign-up/email `
  -H "Content-Type: application/json" `
  -d '{"name":"Ed","email":"ed@studio.com","password":"s3cret-pass"}'
# -> {"token":"...","user":{"id":"...","email":"ed@studio.com",...}}
$tok = "<token>"
curl -s http://127.0.0.1:18099/api/auth/get-session -H "Authorization: Bearer $tok"
# -> {"session":{"expiresAt":"...","userId":"..."},"user":{...}}
```

## 4. Sidecar service

```powershell
cd <repo>
pip install ./service
$env:PYTHONPATH = "service"
$env:TEMPO_AUTH_MODE = "on"
$env:TEMPO_AUTH_URL = "http://127.0.0.1:18099"
$env:TEMPO_BACKEND = "local"   # offline dev; "http" + TEMPO_BACKEND_URL/TOKEN for Modal
python -m uvicorn tempo_service.app:app --host 127.0.0.1 --port 8765
```

Checklist: `GET /health` → ok; panel Sign in with the user from §3 →
`GET /auth/me` → `logged_in:true`; without login, `/sync` → `401
AUTH_REQUIRED`. `auth_mode=off` leaves everything open (dev/tests only).

## 5. Modal backend deploy

```powershell
pip install modal
modal setup                       # token, never in git
modal secret create tempo-secrets BACKEND_TOKEN="<random-32+>"
modal deploy modal_backend/modal_app.py
```

This creates Volumes `tempo-artifacts` / `tempo-checkpoints`, the T4
`run_stage` function, and the ASGI `api` endpoint. Verify decorator names
against https://modal.com/docs/guide on first deploy. Note the printed
HTTPS URL, then point the sidecar at it:

```powershell
$env:TEMPO_BACKEND = "http"
$env:TEMPO_BACKEND_URL = "https://<app>--api.modal.run"
$env:TEMPO_BACKEND_TOKEN = "<same BACKEND_TOKEN>"
```

`GET /health` on the sidecar must now show
`backend:{reachable:true,gpu:true}`. GPU stage bodies execute here for the
first time — run the **GPU trial**: index a 2-min clip, record GPU-minutes
per footage-minute (this number prices your plans at 3–5× blended cost),
and confirm checkpoint resume by cancelling mid-index and re-submitting.

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
2. Search → skeleton (≥200ms) → cards with thumbs + sorted bars.
3. Click a card → layer trimmed `[start_s,end_s]` at playhead, viewer on
   first frame, selected, one Ctrl+Z removes all.
4. Quota: import a 2nd file on free → `403 QUOTA_EXCEEDED` inline;
   unchanged re-sync still passes; Retry/Resume recover failures.
5. Sign out → `401 AUTH_REQUIRED` inline login; sign in → resumes.

## 9. Release (see docs/release.md for the full gate list)

Version map in one commit (`pyproject` ↔ manifest ↔ panel `?v=` +
`PANEL_VERSION` ↔ `auth/package.json`) → all gates green → smoke on
oldest+newest AE → `packaging\build-windows.ps1` + `zxp-sign.ps1` →
beta channel → 48h Sentry-quiet → stable. Repackage ZXP ≥60 days before
cert expiry (expired cert = silently dead panel).

## Troubleshooting (all observed in testing)

| `modal stage needs X ... (import failed: ...)` | Image missing a dep or system lib | Suffix names the root cause (often a `.so` — add the apt lib to `modal_app.py`); redeploy |
| Symptom | Cause | Fix |
|---|---|---|
| `sync +0`, `evalScript raw len=0` | CEP skipped ScriptPath eval | Loader self-heals (watch `loader:` lines); else reinstall + full AE quit |
| `Expected: )` running host scripts | Regex literal in ES3 | No regex in `host.jsx` (ESLint gate enforces) |
| `footage not on Drive/storage` | Bytes never uploaded | Copy to the exact key, or configure storage + Retry |
| `403 QUOTA_EXCEEDED` | Free tier: 1 footage / 7 min | Prune project or upgrade plan |
| `401 AUTH_REQUIRED` | No session | Sign in (panel) |
| `BACKEND_ASLEEP/TIMEOUT` | Workers cold/slow | Wait + poll; warm pool before launch pricing |
| Old UI after update | CEF cache | `?v=` bump (in map) + full AE quit |
| `MODEL_NOT_LOADED` 503 | No cached text model | Local path needs weights; backend path needs warm pool |
