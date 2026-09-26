# Release checklist (AGENTS.md §11 Definition of Done, expanded)

## Version map (bump together, one commit)

| Surface | File | Field |
|---|---|---|
| Sidecar | `service/pyproject.toml` | `version` |
| Panel bundle | `panel/CSXS/manifest.xml` | `ExtensionBundleVersion` + `Version` |
| Panel cache | `panel/www/index.html` | `?v=` on css/js |
| Panel debug stamp | `panel/www/panel.js` | `PANEL_VERSION` |

## Pre-release gates (all green, in order)

1. `python -m pytest service/tests -q` (golden + parity + contracts).
2. `python -m ruff check service modal_backend` (CI mirrors this).
3. `npx eslint panel/host/host.jsx panel/host/ae_smoke.jsx` (ES3 gate).
4. `node --check` on `panel/www/*.js`.
5. `ae_smoke.jsx` on the **oldest and newest** claimed AE (`docs/ae-smoke.md`,
   sign name/date/version) — AE has no cheap CI automation; manual is honest.
6. Panel screenshot vs §6 anti-slop list (reviewer rejects gradients, pills,
   emoji, spinners-where-skeletons-belong on sight).
7. Fresh-machine install: Velopack Setup → import → index → search
   → click-insert → single-undo. Then auto-update to the previous build and
   back (channels).

## Signing & expiry watch

- ZXP: timestamped signature; calendar reminder **60 days before** cert
  expiry (expired = panel silently dead, no user warning).
- Sidecar/MSI: EV cert; SmartScreen reputation accrues per binary.
- Secrets rotation rehearsed: Modal Secret, R2/B2 keys, Stripe webhooks.

## Rollout

- Ship panel + sidecar to the beta channel first; promote to stable after
  48h without new Sentry issues. Rollback = republish previous channel
  build (Velopack) / previous ZXP (Exchange).
