"""Single-worker background job queue (AGENTS.md §3.2).

Jobs run strictly sequentially in one daemon thread: uploads share one link
to the engine and the engine indexes one footage at a time. `POST /sync`
may enqueue many; they process one by one.

Each job carries `upload` + the engine's stages with `{stage, done, total}`
progress that mirrors real work only (AGENTS.md F4 — no fake timers). Stage
names are never duplicated here: they come from the engine's /v1/health
(`set_stage_source`), and any stage the engine reports is mirrored as-is.
The handoff (proxy.handle) registers as the handler; without one, jobs wait
in `queued` state instead of reporting fake progress.
"""

import logging
import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

log = logging.getLogger("tempo.jobs")

UPLOAD_STAGE = "upload"  # stage 0 (§3.2): bytes sent to the engine, before its own stages

# Handler signature: fn(job, progress) where
# progress(stage_name, done, total) records real stage progress.
Handler = Callable[["Job", Callable[[str, int, int], None]], None]


@dataclass
class Job:
    job_id: str
    footage_key: str
    # queued|uploading|queued-for-backend|running|done|error|cancelled
    state: str = "queued"
    stage_names: list[str] = field(default_factory=lambda: [UPLOAD_STAGE])
    stages: dict[str, dict] = field(default_factory=dict)  # insertion order = display order
    error: str | None = None
    # The kind of failure, in the panel's vocabulary (proxy.REASONS). Read off the
    # exception rather than imported: proxy imports this module. None when whatever
    # raised was not a handoff failure, which the panel renders as its fallback.
    reason: str | None = None
    reused: bool = False  # engine already held a ready index for this content

    def __post_init__(self) -> None:
        for name in self.stage_names:
            self.ensure_stage(name)

    def ensure_stage(self, name: str) -> dict:
        return self.stages.setdefault(name, {"name": name, "state": "pending", "done": 0, "total": 0})

    def to_status(self) -> dict:
        return {
            "job_id": self.job_id,
            "footage_key": self.footage_key,
            "state": self.state,
            "reused": self.reused,
            "stages": [dict(st) for st in self.stages.values()],
            "error": self.error,
            "reason": self.reason,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._handler: Handler | None = None
        self._stage_source: Callable[[], list[str]] = lambda: [UPLOAD_STAGE]
        self._worker = threading.Thread(target=self._run, daemon=True, name="tempo-jobs")
        self._worker.start()

    def register_handler(self, handler: Handler) -> None:
        """Register the handoff runner (proxy.handle). One handler only."""
        self._handler = handler

    def set_stage_source(self, source: Callable[[], list[str]]) -> None:
        """Stage names for new jobs (`upload` + the engine's stages, from its health)."""
        self._stage_source = source

    def enqueue(self, footage_key: str) -> str:
        job_id = "job_" + uuid.uuid4().hex[:8]
        job = Job(job_id=job_id, footage_key=footage_key, stage_names=self._stage_source())
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put(job_id)
        log.info("enqueued %s for footage %s", job_id, footage_key)
        return job_id

    # States holding a claim on a footage key: a second enqueue for the same
    # key must reuse the live job, never mint a duplicate full pipeline run.
    ACTIVE_STATES = ("queued", "uploading", "running", "queued-for-backend")

    def active_job_for(self, footage_key: str) -> str | None:
        """Newest non-terminal job id for the key, or None. Guards the sync
        handler and retries against double-enqueue (transient stat flips,
        Retry-spam, restart races all converge here)."""
        with self._lock:
            # Reversed insertion order: newest live job wins (ids are random
            # hex, so lexicographic order would be meaningless).
            for job_id in reversed(list(self._jobs)):
                job = self._jobs[job_id]
                if job.footage_key == footage_key and job.state in self.ACTIVE_STATES:
                    return job_id
        return None

    def cancel(self, job_id: str) -> str:
        """Drop a job that hasn't started: 'cancelled'. Returns an outcome
        the route maps to HTTP: 'cancelled' | 'missing' | 'terminal' |
        'running'. Running jobs (local or backend-backed) can't be stopped
        mid-thread — they run to completion, which is always a valid result."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return "missing"
            if job.state in ("done", "error", "cancelled"):
                return "terminal"
            if job.state != "queued":
                return "running"
            job.state = "cancelled"
            job.error = "cancelled by user"
            return "cancelled"

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def progress(self, job_id: str, stage: str, done: int, total: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.ensure_stage(stage).update(state="running", done=int(done), total=int(total))

    def _set(self, job_id: str, **fields) -> None:  # type: ignore[no-untyped-def]
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def _mark_stage(self, job_id: str, stage: str, state: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            entry = job.ensure_stage(stage)
            entry["state"] = state
            if state == "done" and entry["total"] and not entry["done"]:
                entry["done"] = entry["total"]

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                if self._handler is None:
                    continue  # no runner yet — stay queued, report honestly
                with self._lock:
                    job = self._jobs.get(job_id)
                if job is None:
                    continue
                if job.state == "cancelled":
                    log.info("job %s cancelled before start; skipping", job_id)
                    continue
                self._set(job_id, state="running")
                log.info("job %s started (footage %s)", job_id, job.footage_key)

                def progress(stage: str, done: int, total: int) -> None:
                    self.progress(job_id, stage, done, total)

                self._handler(job, progress)
                for name in list(job.stages):
                    self._mark_stage(job_id, name, "done")
                self._set(job_id, state="done")
                log.info("job %s done", job_id)
            except Exception as exc:  # runner failures are job errors, not crashes
                log.exception("job %s failed: %s", job_id, exc)
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        for st in job.stages.values():
                            if st["state"] == "running":
                                st["state"] = "error"
                        job.state = "error"
                        job.error = str(exc)
                        # An unnamed exception (not a HandoffError) leaves this None,
                        # which is the honest answer: we know it failed, not why.
                        job.reason = getattr(exc, "reason", None)
            finally:
                self._queue.task_done()


jobs = JobManager()
