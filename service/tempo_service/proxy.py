"""Colab handoff worker (ADR-0002, testing workflow).

Single-worker proxy queue: local job → Drive check → POST /index → poll
Colab at 500 ms → mirror stages → mark registry ready. Colab asleep at
handoff → local job waits in `queued-for-colab` (retried each poll), never
failed. Missing Drive file → job error with the exact Drive copy hint.

When no Colab URL is configured, delegates to the local indexer pipeline
(P3) so AE testing still works without the cloud.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger("tempo.proxy")

POLL_S = 0.5
HANDOFF_RETRIES = 120  # ~60 s of Colab-asleep retries per poll loop iteration set


def _local_handler():  # type: ignore[no-untyped-def]
    from .indexer.pipeline import register as _  # noqa: F401 (ensures registration)

    from . import jobs as _jobs

    return _jobs.jobs._handler


def handle(job, progress) -> None:  # type: ignore[no-untyped-def]
    from . import colab as colab_module
    from . import drive as drive_module
    from . import jobs as jobs_module
    from . import registry as registry_module
    from .config import settings

    if not colab_module.configured(settings.colab_url):
        handler = _local_handler()
        if handler is None:
            from .indexer.pipeline import register as register_pipeline

            register_pipeline()
            handler = jobs_module.jobs._handler
        if handler is None:
            raise RuntimeError("no pipeline handler registered")
        # Local path has no Drive leg — mark upload done immediately.
        try:
            progress("upload", 1, 1)
        except Exception:
            pass
        handler(job, progress)
        return

    registry = registry_module.load_registry()
    entry = registry.get(job.footage_key, {})
    drive_path = entry.get("drive_path") or drive_module.drive_path_for(
        job.footage_key, entry.get("path", "")
    )
    try:
        _handoff(job, progress, drive_path, entry)
    except Exception as exc:
        # Honest terminal state for Retry: entry keeps the message, job keeps
        # the failed stages (jobs._run marks them). Re-raised so the job
        # itself lands in `error` too.
        try:
            reg = registry_module.load_registry()
            ent = reg.get(job.footage_key)
            if ent is not None:
                ent["state"] = "error"
                ent["error"] = str(exc)[:500]
                registry_module.save_registry(reg)
        except Exception:
            pass
        raise


def _handoff(job, progress, drive_path: str, entry: dict) -> None:  # type: ignore[no-untyped-def]
    from . import colab as colab_module
    from . import jobs as jobs_module
    from . import registry as registry_module
    from .config import settings

    jobs_module.jobs._set(job.job_id, state="queued-for-colab")
    try:
        progress("upload", 0, 1)
    except Exception:
        pass

    ok, status, body, code = colab_module.index(
        settings.colab_url, settings.colab_token, drive_path, settings.colab_timeout_s
    )
    if not ok:
        if code == "COLAB_ASLEEP":
            raise RuntimeError(
                "Colab asleep at handoff (queued-for-colab). Start the Colab server and retry."
            )
        raise RuntimeError(f"Colab handoff failed ({code or status}). Check TEMPO_COLAB_URL/TOKEN.")
    colab_id = (body or {}).get("job_id", "")
    if not colab_id:
        raise RuntimeError("Colab handoff returned no job_id.")

    try:
        progress("upload", 1, 1)
    except Exception:
        pass
    jobs_module.jobs._set(job.job_id, state="running")

    while True:
        ok, status, cjob, code = colab_module.job_status(
            settings.colab_url, settings.colab_token, colab_id, settings.colab_timeout_s
        )
        if not ok:
            if code == "COLAB_ASLEEP":
                jobs_module.jobs._set(job.job_id, state="queued-for-colab")
                time.sleep(2.0)
                continue
            raise RuntimeError(f"Colab poll failed ({code or status}).")
        for st in (cjob or {}).get("stages", []):
            name = st.get("name", "")
            if name in jobs_module.STAGES:
                if st.get("state") == "running":
                    try:
                        progress(name, int(st.get("done", 0)), int(st.get("total", 0)))
                    except Exception:
                        pass
                elif st.get("state") == "done":
                    jobs_module.jobs._mark_stage(job.job_id, name, "done")
                elif st.get("state") == "error":
                    jobs_module.jobs._mark_stage(job.job_id, name, "error")
        state = (cjob or {}).get("state", "")
        if state == "done":
            break
        if state == "error":
            err = (cjob or {}).get("error") or "colab job failed"
            if "not on Drive" in err and "Drive/" not in err:
                err += f" (copy local file to Drive/{drive_path})"
            raise RuntimeError(err)
        time.sleep(POLL_S)

    # Mark registry ready from Colab completion (shot_count/duration honest).
    registry = registry_module.load_registry()
    entry = registry.get(job.footage_key)
    if entry is not None:
        entry["state"] = "ready"
        entry["shot_count"] = int((cjob or {}).get("shot_count", entry.get("shot_count", 0)))
        dur = (cjob or {}).get("duration_s", 0.0) or 0.0
        try:
            entry["duration_s"] = float(dur)
        except (TypeError, ValueError):
            pass
        from .registry import now_iso

        entry["indexed_at"] = now_iso()
        registry_module.save_registry(registry)
    log.info("proxy job %s done via colab %s", job.job_id, colab_id)


def register() -> None:
    from . import jobs as jobs_module

    jobs_module.jobs.register_handler(handle)
