"""Engine handoff worker (ADR-0008, D16).

One sidecar job per footage, run by the single worker:

  1. content id of the local file (size + first/last 4 MiB — no GB hashing)
  2. engine library lookup:
       ready     → footage is ready now (`reused`): no upload, no GPU work
       indexing  → attach to the engine's live job
       otherwise → upload (resumable, from the engine's offset) if the engine
                   needs the bytes, then POST /v1/index
  3. poll the engine job, mirroring its stages with real units
  4. sync display thumbs down (one tar, keyed by content id)
  5. registry entry → ready (content_id, shot_count, duration_s)

Engine asleep/warming → the job waits in `queued-for-backend` (never
failed). Transient unreachable/timeouts get `backend_poll_miss_retries`
before the job fails with an honest message; Retry picks up where it left off
(upload offset, stage cache).
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import tarfile
import time
from collections.abc import Callable

from . import fingerprint
from . import jobs as jobs_module
from . import registry as registry_module
from .backends import ASLEEP, TRANSPORT_CODES, BackendProvider, Reply, get_provider
from .config import settings

log = logging.getLogger("tempo.proxy")

UPLOAD = jobs_module.UPLOAD_STAGE
MB = 1024 * 1024
THUMB_NAME = re.compile(r"\d{1,7}\.jpg")


class HandoffError(RuntimeError):
    pass


def _set_state(job, state: str) -> None:  # type: ignore[no-untyped-def]
    job.state = state
    jobs_module.jobs._set(job.job_id, state=state)


def _call(job, what: str, fn: Callable[[], Reply]) -> Reply:  # type: ignore[no-untyped-def]
    """Run one engine call. ASLEEP waits (queued-for-backend) without limit; unreachable/timeout
    retry `backend_poll_miss_retries` times. Application errors return to the caller."""
    misses = 0
    prior = job.state
    while True:
        reply = fn()
        if reply.ok or reply.code not in TRANSPORT_CODES:
            if job.state == "queued-for-backend" and prior != "queued-for-backend":
                _set_state(job, prior)
            return reply
        if reply.code == ASLEEP:
            _set_state(job, "queued-for-backend")
        else:
            misses += 1
            log.info("job %s: %s miss %d/%d (%s)", job.job_id, what, misses,
                     settings.backend_poll_miss_retries, reply.code)
            if misses >= settings.backend_poll_miss_retries:
                raise HandoffError(f"{what} failed: {reply.code} {reply.message}".strip())
        time.sleep(settings.backend_asleep_wait_s)


def _update_entry(key: str, **fields) -> None:  # type: ignore[no-untyped-def]
    registry = registry_module.load_registry()
    entry = registry.get(key)
    if entry is not None:
        entry.update(fields)
        registry_module.save_registry(registry)


def _upload(job, provider: BackendProvider, path: str, cid: str, offset: int, progress) -> None:  # type: ignore[no-untyped-def]
    size = os.path.getsize(path)
    name = os.path.basename(path)
    chunk = settings.upload_chunk_mb * MB
    _set_state(job, "uploading")
    progress(UPLOAD, offset, size)
    with open(path, "rb") as f:
        while offset < size:
            f.seek(offset)
            data = f.read(chunk)
            reply = _call(job, "upload", lambda: provider.upload_chunk(cid, offset, size, name, data))
            if reply.code == "OFFSET_MISMATCH":
                offset = int(json.loads(reply.message)["received"])  # resume where the engine is
                log.info("job %s: upload resumes at %d", job.job_id, offset)
            elif not reply.ok:
                raise HandoffError(f"upload rejected: {reply.code} {reply.message}".strip())
            else:
                offset = int(reply.body["received"])
            progress(UPLOAD, offset, size)
    log.info("job %s: uploaded %s (%d bytes)", job.job_id, cid, size)


def _submit(job, provider: BackendProvider, path: str, cid: str, progress) -> dict:  # type: ignore[no-untyped-def]
    reply = _call(job, "index", lambda: provider.submit_index(cid))
    if reply.code == "SOURCE_MISSING":  # raw purged between lookup and submit: send it again
        _upload(job, provider, path, cid, 0, progress)
        reply = _call(job, "index", lambda: provider.submit_index(cid))
    if not reply.ok:
        raise HandoffError(f"index request rejected: {reply.code} {reply.message}".strip())
    return reply.body


def _poll(job, provider: BackendProvider, engine_job: str, progress) -> dict:  # type: ignore[no-untyped-def]
    _set_state(job, "running")
    while True:
        reply = _call(job, "poll", lambda: provider.job_status(engine_job))
        if not reply.ok:
            raise HandoffError(f"engine job {engine_job}: {reply.code} {reply.message}".strip())
        body = reply.body
        for st in body.get("stages", []):
            name, state = st.get("name", ""), st.get("state")
            if state == "running":
                progress(name, int(st.get("done", 0)), int(st.get("total", 0)))
            elif state in ("done", "error"):
                jobs_module.jobs._mark_stage(job.job_id, name, state)
        if body.get("state") == "done":
            return body
        if body.get("state") == "error":
            raise HandoffError(body.get("error") or "engine job failed")
        time.sleep(settings.job_poll_s)


def sync_thumbs(provider: BackendProvider, cid: str, force: bool = False) -> int:
    """Extract the engine's thumbs.tar into the local cache. Never fails the job (lazy fallback)."""
    out = registry_module.thumbs_dir(cid)
    if not force and out.is_dir() and any(out.glob("*.jpg")):
        return 0
    reply = provider.thumbs_tar(cid)
    if not reply.ok:
        log.warning("thumb sync %s failed (%s); thumbs load lazily", cid, reply.code)
        return 0
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(reply.body), mode="r:") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not THUMB_NAME.fullmatch(member.name):
                continue  # only flat `<shot_id>.jpg` names: nothing can escape the cache dir
            data = tar.extractfile(member)
            if data is not None:
                (out / member.name).write_bytes(data.read())
                count += 1
    log.info("thumb sync %s: %d thumbs", cid, count)
    return count


def _finish(job, provider: BackendProvider, cid: str, stats: dict, reused: bool) -> None:  # type: ignore[no-untyped-def]
    sync_thumbs(provider, cid, force=not reused)
    job.reused = reused
    _update_entry(job.footage_key, state="ready", content_id=cid, reused=reused,
                  shot_count=int(stats.get("shot_count", 0)),
                  duration_s=float(stats.get("duration_s", 0.0)),
                  indexed_at=registry_module.now_iso())
    log.info("job %s: %s ready (%s)", job.job_id, job.footage_key, "reused index" if reused else "indexed")


def _handoff(job, progress, provider: BackendProvider, entry: dict) -> None:  # type: ignore[no-untyped-def]
    path = entry.get("path", "")
    if not path or not os.path.isfile(path):
        raise HandoffError(f"source file not found on disk: {path}")
    cid = fingerprint.content_id(path)
    _update_entry(job.footage_key, content_id=cid)
    log.info("job %s: %s -> content %s", job.job_id, job.footage_key, cid)

    lib = _call(job, "library", lambda: provider.library(cid))
    if not lib.ok:
        raise HandoffError(f"library lookup failed: {lib.code} {lib.message}".strip())
    info = lib.body
    if info["state"] == "ready":
        jobs_module.jobs._mark_stage(job.job_id, UPLOAD, "done")
        _finish(job, provider, cid, info, reused=True)
        return

    engine_job = info.get("job_id") if info["state"] == "indexing" else None
    if engine_job is None:
        if info.get("needs_upload"):
            resume = int(info.get("received", 0)) if info["state"] == "partial" else 0
            _upload(job, provider, path, cid, resume, progress)
        jobs_module.jobs._mark_stage(job.job_id, UPLOAD, "done")
        submitted = _submit(job, provider, path, cid, progress)
        if submitted.get("state") == "done":
            ready = _call(job, "library", lambda: provider.library(cid))
            _finish(job, provider, cid, ready.body if ready.ok else {}, reused=True)
            return
        engine_job = submitted["job_id"]
    else:
        jobs_module.jobs._mark_stage(job.job_id, UPLOAD, "done")
    log.info("job %s: engine job %s", job.job_id, engine_job)
    done = _poll(job, provider, engine_job, progress)
    _finish(job, provider, cid, done, reused=False)


def handle(job, progress) -> None:  # type: ignore[no-untyped-def]
    provider = get_provider(settings)
    try:
        if provider is None:
            raise HandoffError("engine not configured: set TEMPO_BREV_INSTANCE or TEMPO_BACKEND_URL")
        entry = registry_module.load_registry().get(job.footage_key)
        if entry is None:
            raise HandoffError(f"unknown footage {job.footage_key}")
        _handoff(job, progress, provider, entry)
    except Exception as exc:
        # Honest terminal state for Retry: the entry keeps the message, the job keeps its
        # failed stages (jobs._run marks them). Re-raised so the job lands in `error`.
        _update_entry(job.footage_key, state="error", error=str(exc)[:500])
        raise


def register() -> None:
    jobs_module.jobs.register_handler(handle)
