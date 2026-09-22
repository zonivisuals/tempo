"""Plans and quota enforcement (ADR-0007).

Free tier (locked): 1 footage, 7 footage-minutes. Plan comes from
settings.plan today (default "free"); Supabase `licenses` rows override it
once billing lands (P3+), without changing this module's checks.

Enforced only when a sync introduces NEW work (added/changed non-empty):
pure unchanged syncs always pass so an over-quota project never bricks the
panel — the user just can't enqueue more until back under quota. Denials
are 403 QUOTA_EXCEEDED with the limit named (panel renders it inline).
"""

PLANS = {
    "free": {"footage": 1, "minutes": 7},
    "pro": {"footage": 50, "minutes": 600},
    "studio": {"footage": 500, "minutes": 6000},
}


def quotas(plan: str) -> dict:
    """Unknown plan names fail closed to free (never fail open to unlimited)."""
    return PLANS.get(plan, PLANS["free"])


def check_new_work(added, changed, unchanged, registry, plan="free"):
    """Gate new indexing work. Returns (ok, code, message)."""
    if not (added or changed):
        return True, "", ""
    active = set(added) | set(changed) | set(unchanged)
    limit = quotas(plan)
    if len(active) > limit["footage"]:
        return (
            False,
            "QUOTA_EXCEEDED",
            f"plan {plan!r} allows {limit['footage']} footage; "
            f"project holds {len(active)}",
        )
    ready_minutes = sum(
        float(registry.get(k, {}).get("duration_s", 0.0) or 0.0)
        for k in active
        if registry.get(k, {}).get("state") == "ready"
    ) / 60.0
    if ready_minutes > limit["minutes"]:
        return (
            False,
            "QUOTA_EXCEEDED",
            f"plan {plan!r} allows {limit['minutes']} footage-minutes; "
            f"ready footage totals {ready_minutes:.1f}",
        )
    return True, "", ""
