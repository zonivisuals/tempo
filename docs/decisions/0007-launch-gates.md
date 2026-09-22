# 0007 — Plans, entitlements, and release gates

**Status:** accepted. **Date:** 2026-09-22.

## Context

Free tier is locked (1 footage, 7 footage-minutes) but nothing enforced it:
any project could enqueue anything, and over-quota states had no honest
surface. Release also lacked gates beyond pytest — the ES3 rule (§7.1) and
the smoke checklist (§9) were unenforced, and packaging was tribal knowledge.

## Decision

- **Entitlements** (`service/tempo_service/entitlements.py`): plan table
  (`free/pro/studio`, unknown names fail closed to free); `/sync` denies
  NEW work with `403 QUOTA_EXCEEDED` naming the limit, before any registry
  mutation or enqueue. Pure unchanged syncs always pass (an over-quota
  project stays viewable, never bricked). Retries bypass (same footage, no
  expansion). Plan source is `settings.plan` today; Supabase `licenses`
  rows override it when billing lands, unchanged checks.
- **Lint gates in CI:** ruff (service + modal_backend, pinned config) and
  the ESLint ES3 gate (`ecmaVersion: 3` + Array-extra/promise bans) for
  `panel/host/*.jsx` — modern syntax fails the build. First run already
  paid off: a latent `np` NameError in the offline indexer plus dead
  imports across old and new code.
- **Packaging as code:** `packaging/build-windows.ps1` (PyInstaller
  `--onedir` + Velopack, version from pyproject — the single source) and
  `packaging/zxp-sign.ps1` (ZXPSignCmd + timestamp + verify), both
  parse-checked in CI, fully built on the release machine. `docs/release.md`
  holds the version map, gate order, cert-expiry watch, and rollout.

## Consequences

- Free tier is real: second footage or >7 ready minutes → inline
  `QUOTA_EXCEEDED`, retryable after pruning/upgrading.
- Every release repeats the same gates; cert expiry is calendared, not
  discovered by users.

## Revisit when

Stripe lands (plan source moves to `licenses`, durations metered),
or Mac support returns (notarization + second installer path).
