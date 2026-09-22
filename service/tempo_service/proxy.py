"""Backend handoff worker (ADR-0004).

Single-worker proxy queue: local job → storage-ref check → POST /index →
poll backend at 500 ms → mirror stages → mark registry ready. Backend asleep
at handoff → local job waits in `queued-for-backend` (retried each poll),
never failed. Missing source file → job error with the exact storage hint.

With backend="local" (default), delegates to the in-process indexer pipeline
(P3) so AE testing still works without the cloud.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger("tempo.proxy")

POLL_S = 0.5


def _local_handler():  # type: ignore[no-untyped-def]
    from .indexer.pipeline import register as _  # noqa: F401 (ensures registration)

    from . import jobs as _jobs

    return _jobs.jobs._handler


def handle(job, progress) -> None:  # type: ignore[no-untyped-def]
    from . import drive as drive_module
    from . import jobs as jobs_module
    from . import registry as registry_module
    from .backends import get_provider
    from .config import settings

    provider = get_provider(
        settings.backend, settings.backend_url, settings.backend_token,
        settings.backend_timeout_s,
    )
    if provider is None:
        if settings.backend == "http":
            log.warning("backend=http but no URL configured; running locally")
        handler = _local_handler()
        if handler is None:
            from .indexer.pipeline import register as register_pipeline

            register_pipeline()
            handler = jobs_module.jobs._handler
        if handler is None:
            raise RuntimeError("no pipeline handler registered")
        # Local path has no upload leg — mark upload done immediately.
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
        _handoff(job, progress, provider, drive_path, entry)
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


def _handoff(job, progress, provider, drive_path: str, entry: dict) -> None:  # type: ignore[no-untyped-def]
    from . import jobs as jobs_module
    from . import registry as registry_module
    from .config import settings
    from .storage import StorageError, get_storage

    jobs_module.jobs._set(job.job_id, state="queued-for-backend")
    storage = get_storage(
        settings.storage_provider, settings.storage_endpoint, settings.storage_bucket,
        settings.storage_key, settings.storage_secret, settings.storage_region,
        settings.storage_presign_ttl,
    )
    if storage is not None:
        # Real byte movement with real progress (ADR-0006). No storage ->
        # manual-copy leg: the backend verifies presence and errors honestly.
        local_path = entry.get("path", "")
        if not local_path:
            raise RuntimeError("registry entry has no local path; cannot upload")
        try:
            storage.upload_file(
                local_path, drive_path,
                progress=lambda d, t: progress("upload", d, t),
            )
        except StorageError as exc:
            raise RuntimeError(str(exc))
    else:
        try:
            progress("upload", 0, 1)
        except Exception:
            pass

    ok, status, body, code = provider.submit_index(drive_path)
    if not ok:
        if code == "BACKEND_ASLEEP":
            raise RuntimeError(
                "Backend asleep at handoff (queued-for-backend). "
                "Start the backend workers and retry."
            )
        raise RuntimeError(f"Backend handoff failed ({code or status}). Check backend config.")
    backend_id = (body or {}).get("job_id", "")
    if not backend_id:
        raise RuntimeError("Backend handoff returned no job_id.")

    # Upload stage already shows real bytes (storage leg) or the 0/1 manual
    # marker — handoff success only flips the job state, never progress.
    jobs_module.jobs._set(job.job_id, state="running")

    while True:
        ok, status, cjob, code = provider.job_status(backend_id)
        if not ok:
            if code == "BACKEND_ASLEEP":
                jobs_module.jobs._set(job.job_id, state="queued-for-backend")
                time.sleep(2.0)
                continue
            raise RuntimeError(f"Backend poll failed ({code or status}).")
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
            err = (cjob or {}).get("error") or "backend job failed"
            if "not on Drive" in err and "Drive/" not in err:
                err += f" (copy local file to Drive/{drive_path})"
            raise RuntimeError(err)
        time.sleep(POLL_S)

    # Retention call (locked): raw upload purged once artifacts persist.
    # Delete failure never fails indexed work — it only warns.
    if storage is not None:
        if settings.storage_retention == "delete":
            try:
                storage.delete_key(drive_path)
                log.info("proxy job %s purged raw %s", job.job_id, drive_path)
            except StorageError as exc:
                log.warning("proxy job %s raw purge failed (%s)", job.job_id, exc)

    # Mark registry ready from backend completion (shot_count/duration honest).
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
    log.info("proxy job %s done via backend %s", job.job_id, backend_id)


def register() -> None:
    from . import jobs as jobs_module

    jobs_module.jobs.register_handler(handle)
