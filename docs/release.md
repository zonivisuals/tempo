# Release checklist (AGENTS.md §11 Definition of Done, expanded)

## Version map (bump together, one commit)

| Surface | File | Field |
|---|---|---|
| Sidecar | `service/pyproject.toml` | `version` |
| Engine | `engine/pyproject.toml` | `version` (index semantics change → also `PIPELINE_VERSION` in `engine/tempo_engine/config.py`, which changes the signature and rebuilds through the stage cache) |
| Panel bundle | `panel/CSXS/manifest.xml` | `ExtensionBundleVersion` + `Version` |
| Panel cache | `panel/www/index.html` | `?v=` on css/js |
| Panel debug stamp | `panel/www/panel.js` | `PANEL_VERSION` |

## Pre-release gates (all green, in order)

1. `python -m pytest service/tests engine/tests -q` (contracts, handoff, golden fusion, FAISS parity).
2. `python -m ruff check service engine` (CI mirrors both, each with its pinned config).
3. `npx eslint panel/host/host.jsx panel/host/ae_smoke.jsx` (ES3 gate).
4. `node --check` on `panel/www/*.js`.
5. Engine on the L4: `engine/deploy/brev-deploy.sh` for the release ref; the
   `prefetch --verify` step and `/v1/health` (`gpu: true`, `query_models: ready`)
   must pass before any client update ships.
6. `ae_smoke.jsx` on the **oldest and newest** claimed AE (`docs/ae-smoke.md`,
   sign name/date/version) — AE has no cheap CI automation; manual is honest.
7. Panel screenshot vs ADR-0011 / `docs/design/panel-ui.md`: reviewer
   rejects glows, pills, emoji, dead controls, and more than two animated
   surfaces at once. A gradient is only ever the mechanism of a loading
   sweep, never a surface treatment.
8. Fresh-machine install: Velopack Setup → import → index → search
   → click-insert → single-undo. Then auto-update to the previous build and
   back (channels).

## Signing & expiry watch

- ZXP: timestamped signature; calendar reminder **60 days before** cert
  expiry (expired = panel silently dead, no user warning).
- Sidecar/MSI: EV cert; SmartScreen reputation accrues per binary.
- Secrets rotation rehearsed: engine token (`engine/deploy/.env` on the instance ↔ sidecar `TEMPO_BACKEND_TOKEN`), Stripe webhooks.

## Rollout

- Ship panel + sidecar to the beta channel first; promote to stable after
  48h without new Sentry issues. Rollback = republish previous channel
  build (Velopack) / previous ZXP (Exchange).
