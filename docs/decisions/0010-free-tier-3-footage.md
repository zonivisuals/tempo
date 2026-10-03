# 0010 — Free tier quota: 3 footage, 120 minutes

**Status:** accepted. **Date:** 2026-09-28. Amends D14 (`0007-launch-gates.md`).

## Context

Free tier locked at 1 footage / 7 minutes blocked the normal two-footage
demo/editing flow twice: first the footage-count gate (`project holds 2`),
then — with the vlog `ready` at 52.7 minutes — the minutes gate. Minutes
7 was incoherent for hour-long vlog footage: any new footage alongside a
ready 52-minute piece 403s.

## Decision

- `PLANS["free"]`: footage 1 → 3, minutes 7 → 120
  (`service/tempo_service/entitlements.py`). Covers the 52-minute vlog plus
  ~1h of further new footage. Pro/studio untouched; unknown plans still
  fail closed to free.
- Enforcement semantics unchanged: new work only, unchanged syncs always pass,
  `403 QUOTA_EXCEEDED` naming the limit, retries bypass.

## Consequences

- Up to 3 footages per free project; the 4th new footage 403s as before.
- Updated together: entitlement tests, `docs/api.md`, `docs/production.md`,
  `AGENTS.md` D14 line, this index.

## Revisit when

Billing lands (plan source moves to `licenses`, durations metered), or the
minutes gate becomes the binding constraint for the target footage lengths.
