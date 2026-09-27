"""Single GPU worker with durable job envelopes (ADR-0008, K3).

One job indexes one content id; jobs run strictly one at a time (GPU memory is
the shared resource). Every transition is written to `jobs/<id>.json`
atomically, so status survives restarts, and on startup jobs that were
`queued` or `running` are re-enqueued — the stage cache turns that into a
resume, not a restart. Submitting a content id that already has a live job
returns that job (no duplicate GPU runs).
"""

import json
import logging
import os
import queue
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path

from .pipeline import Reporter

log = logging.getLogger("tempo.engine.jobs")

JOBS_DIR = "jobs"
LIVE = ("queued", "running")
ERROR_TAIL = 1200
ERROR_MAX = 2000

Runner = Callable[[str, Reporter], dict]


class EngineJobs:
    def __init__(self, root: Path, stages: list[str], runner: Runner) -> None:
        self.dir = Path(root) / JOBS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stages = list(stages)
        self.runner = runner
        self._jobs: dict[str, dict] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._started = False

    # --- persistence -------------------------------------------------------
    def _save(self, job: dict) -> None:
        path = self.dir / f"{job['job_id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job), encoding="utf-8")
        os.replace(tmp, path)

    def _snapshot(self, job: dict) -> dict:
        return {**job, "stages": [dict(s) for s in job["stages"]]}

    def recover(self) -> int:
        """Load every envelope; re-enqueue the ones a restart interrupted."""
        loaded = []
        for path in self.dir.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(job, dict) and job.get("job_id") == path.stem:
                loaded.append(job)
        resumed = 0
        with self._lock:
            for job in sorted(loaded, key=lambda j: j.get("created_at", 0)):
                self._jobs[job["job_id"]] = job
                if job.get("state") in LIVE:
                    job["state"] = "queued"
                    for s in job["stages"]:
                        if s["state"] == "running":
                            s["state"] = "pending"
                    self._save(job)
                    self._queue.put(job["job_id"])
                    resumed += 1
        if resumed:
            log.info("recovered %d interrupted job(s)", resumed)
        return resumed

    # --- queries -----------------------------------------------------------
    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._snapshot(job) if job else None

    def _latest_for(self, cid: str, states: tuple[str, ...] | None = None) -> dict | None:
        for job in reversed(list(self._jobs.values())):
            if job["content_id"] == cid and (states is None or job["state"] in states):
                return job
        return None

    def live_for(self, cid: str) -> str | None:
        with self._lock:
            job = self._latest_for(cid, LIVE)
            return job["job_id"] if job else None

    def last_for(self, cid: str) -> dict | None:
        with self._lock:
            job = self._latest_for(cid)
            return self._snapshot(job) if job else None

    # --- commands ----------------------------------------------------------
    def submit(self, cid: str) -> dict:
        with self._lock:
            live = self._latest_for(cid, LIVE)
            if live:
                return self._snapshot(live)
            job = {"job_id": "ejob_" + uuid.uuid4().hex[:8], "content_id": cid, "state": "queued",
                   "stages": [{"name": n, "state": "pending", "done": 0, "total": 0} for n in self.stages],
                   "error": None, "shot_count": 0, "duration_s": 0.0, "fps": 0.0,
                   "created_at": time.time()}
            self._jobs[job["job_id"]] = job
            self._save(job)
        self._queue.put(job["job_id"])
        log.info("job %s queued for %s", job["job_id"], cid)
        return self._snapshot(job)

    def start(self) -> None:
        if not self._started:
            self._started = True
            threading.Thread(target=self._run, daemon=True, name="tempo-engine-jobs").start()

    # --- worker ------------------------------------------------------------
    def _stage(self, job: dict, name: str) -> dict | None:
        return next((s for s in job["stages"] if s["name"] == name), None)

    def _progress(self, job_id: str, name: str, done: int, total: int) -> None:
        with self._lock:
            job = self._jobs[job_id]
            st = self._stage(job, name)
            if st is not None:
                st.update(state="running", done=int(done), total=int(total))
                self._save(job)

    def _done(self, job_id: str, name: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            st = self._stage(job, name)
            if st is not None:
                st["state"] = "done"
                if st["total"] and st["done"] < st["total"]:
                    st["done"] = st["total"]
                self._save(job)
        log.info("job %s: stage %s done", job_id, name)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is None or job["state"] not in LIVE:
                        continue
                    job["state"] = "running"
                    self._save(job)
                    cid = job["content_id"]
                log.info("job %s started (%s)", job_id, cid)
                report = Reporter(progress=lambda st, d, t: self._progress(job_id, st, d, t),
                                  done=lambda st: self._done(job_id, st))
                summary = self.runner(cid, report)
                with self._lock:
                    for s in job["stages"]:
                        s["state"] = "done"
                    job.update(state="done", shot_count=int(summary.get("shot_count", 0)),
                               duration_s=float(summary.get("duration_s", 0.0)),
                               fps=float(summary.get("fps", 0.0)))
                    self._save(job)
                log.info("job %s done", job_id)
            except Exception as exc:  # a failed job is a job error, never a worker crash
                log.exception("job %s failed: %s", job_id, exc)
                tail = traceback.format_exc(limit=5)[-ERROR_TAIL:]
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        for s in job["stages"]:
                            if s["state"] == "running":
                                s["state"] = "error"
                        job.update(state="error", error=f"{exc}\n{tail}"[:ERROR_MAX])
                        self._save(job)
            finally:
                self._queue.task_done()
