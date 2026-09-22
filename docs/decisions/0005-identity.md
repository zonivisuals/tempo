# 0005 — Better Auth identity, sidecar session gate

**Status:** accepted. **Date:** 2026-09-22.

## Context

Production needs accounts (free-tier quotas, seats, billing, abuse control)
but the sidecar must stay simple and offline-capable for dev. Managed auth
(Clerk/Auth0/Supabase Auth) charges per MAU and holds our user table hostage;
hand-rolled passwords are a breach waiting to happen.

## Decision

- **Better Auth 1.7.5** (self-hosted, open source) in `auth/` (Node 20,
  Express, Postgres): email+password + Google/GitHub, `bearer()` + `jwt()`
  plugins. Endpoint shapes pinned live against the package
  (`/sign-up/email`, `/sign-in/email`, `/get-session`, `/token` — see
  `auth/README.md`), never guessed.
- **Supabase Postgres** hosts data only: Better Auth tables via its CLI
  (`npm run migrate`), app tables (`licenses`) hand-written in
  `supabase/licenses.sql`. Supabase Auth itself is NOT used (no per-MAU
  meter, no second session system).
- **Sidecar gate:** `service/tempo_service/auth.py` validates opaque session
  tokens against `GET /api/auth/get-session` (Bearer) and caches by
  `expiresAt` (7-day sessions = genuine offline grace). `/sync`, `/search`,
  `/jobs/*`, retries require it (`401 AUTH_REQUIRED`) when `auth_mode=on`
  (dev default `off`). `/health`, `/footage`, `/thumb`, `/host` stay public
  (pre-login loader, headerless `<img>` tags, local reads).
- **Panel holds no tokens** (memory only, nothing in localStorage): sign-in
  posts credentials to the sidecar over localhost; sessions persist in the
  OS keychain (`keyring`: Windows Credential Manager, verified roundtrip).
  Single-user box: header token wins, keychain session backs it up.
- JWT plugin reserved for service-to-service (gateway ↔ backend); opaque
  sessions keep crypto out of the sidecar until then.

## Consequences

- New service dep: `keyring`. New infra: `auth/` Node service + Postgres.
  Tests pin every wire shape; unknown shapes fail closed.
- Seats/entitlements enforcement and social-login UI polish land in P3.

## Revisit when

MAU or session volume justifies managed auth, or Postgres needs leaving
Supabase — Better Auth migrates with its Kysely adapter, no client changes.
