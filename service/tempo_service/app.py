"""FastAPI wiring (AGENTS.md §2.2, §3.1).

The sidecar holds no model weights and no scoring (ADR-0008): indexing and
search run on the engine. Lifespan wires the handoff worker, the Brev
port-forward supervisor (when an instance is configured) and a background
engine prober whose cache serves /health instantly and feeds the engine's
stage names to new jobs.
"""

import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from . import jobs as jobs_module
from . import registry as registry_module
from .backends import ASLEEP, TIMEOUT, get_provider
from .config import settings
from .schemas import (
    BackendStatus,
    ErrorBody,
    ErrorEnvelope,
    FootageInfo,
    HealthResponse,
    JobRetryResponse,
    JobStatus,
    SearchResponse,
    SearchResult,
    SyncRequest,
    SyncResponse,
)
from .tunnel import Tunnel

log = logging.getLogger("tempo")
logging.basicConfig(level=settings.log_level)

KEY_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
# content_id is sha1(...)[:16] — 16 lowercase hex. Mirrors the engine's
# fingerprint.valid so both ends of the contract agree on what a content id is.
CONTENT_ID_RE = re.compile(r"[0-9a-f]{16}")
THUMB_CACHE = "public, max-age=86400"


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content=ErrorEnvelope(error=ErrorBody(code=code, message=message)).model_dump())


def _backend_error(code: str | None, what: str) -> JSONResponse:
    return _error(504 if code == TIMEOUT else 502, code or "BACKEND_UNREACHABLE", what)


_backend_status: dict = {"reachable": False, "gpu": False, "signature": "", "stages": [], "checked_at": 0.0}
_backend_lock = threading.Lock()
_prober_started = False
_tunnel: Tunnel | None = None


def _probe_backend_once() -> dict:
    """One synchronous engine probe. Never raises, never logs tokens."""
    try:
        provider = get_provider(settings, settings.backend_health_timeout_s)
        if provider is None:
            return {"reachable": False, "gpu": False, "signature": "", "stages": []}
        return provider.health()
    except Exception as exc:  # defensive: misconfig must not crash lifespan
        log.warning("engine probe crashed (%s)", exc)
        return {"reachable": False, "gpu": False, "signature": "", "stages": []}


def _refresh_backend_status() -> dict:
    probe = _probe_backend_once()
    with _backend_lock:
        # Keep the last known stage list while the engine is unreachable.
        stages = probe.get("stages") or _backend_status["stages"]
        _backend_status.update({**probe, "stages": stages, "checked_at": time.monotonic()})
        return dict(_backend_status)


def _job_stage_names() -> list[str]:
    with _backend_lock:
        return [jobs_module.UPLOAD_STAGE, *_backend_status["stages"]]


def _tunnel_state() -> str:
    return _tunnel.state if _tunnel is not None else "off"


def _start_tunnel() -> None:
    global _tunnel
    if settings.brev_instance and _tunnel is None:
        _tunnel = Tunnel(settings.brev_cli, settings.brev_instance, settings.tunnel_local_port,
                         settings.tunnel_remote_port, settings.tunnel_backoff_min_s,
                         settings.tunnel_backoff_max_s)
        _tunnel.start()


def _start_backend_prober() -> None:
    """Background prober (daemon): refreshes the cached engine status every interval
    and logs only on flips. GET /health serves the cache instantly — never a probe
    per panel poll against a cold or stopped instance."""
    global _prober_started
    if _prober_started:
        return
    _prober_started = True

    def loop() -> None:
        last = None
        while True:
            try:
                st = _refresh_backend_status()
                flip = (st["reachable"], st["gpu"], st["signature"])
                if flip != last:
                    log.info("engine: reachable=%s gpu=%s signature=%s tunnel=%s",
                             st["reachable"], st["gpu"], st["signature"] or "-", _tunnel_state())
                    last = flip
            except Exception as exc:  # thread must never die
                log.warning("engine prober error (%s)", exc)
            time.sleep(settings.backend_health_interval_s)

    threading.Thread(target=loop, daemon=True, name="tempo-backend-prober").start()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Official FastAPI lifespan pattern: setup before yield, cleanup after.
    # https://fastapi.tiangolo.com/advanced/events/
    from urllib.parse import urlsplit

    log.info("tempo startup: artifact_root=%s format_version=%d engine=%s brev=%s",
             settings.artifact_root, settings.format_version,
             urlsplit(settings.engine_url).netloc or "(unset)", settings.brev_instance or "-")
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    from .proxy import register as register_proxy

    register_proxy()
    jobs_module.jobs.set_stage_source(_job_stage_names)
    _start_tunnel()
    _start_backend_prober()
    yield
    if _tunnel is not None:
        _tunnel.stop()
    log.info("tempo shutdown")


def create_app() -> FastAPI:
# No auth wall: the sidecar serves one local editor over 127.0.0.1
    # (see docs/decisions/0005-identity.md - identity removed).
    # Every route below is public on localhost by design.
    #
    # docs_url/redoc_url/openapi_url are off: with no auth wall they hand any
    # process on the machine a complete map of every route, parameter and model
    # for free. docs/api.md is the contract of record.
    app = FastAPI(
        title="Tempo",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        # Cached engine status (background prober); a synchronous probe only
        # runs when the cache never populated (first request before lifespan).
        with _backend_lock:
            cached = dict(_backend_status)
        if cached["checked_at"] <= 0:
            cached = _refresh_backend_status()
        return HealthResponse(
            status="ok",
            artifact_root=str(settings.artifact_root),
            backend=BackendStatus(reachable=cached["reachable"], gpu=cached["gpu"],
                                  tunnel=_tunnel_state(), signature=cached["signature"]),
        )

    @app.post("/sync", response_model=SyncResponse)
    def sync(body: SyncRequest) -> SyncResponse:
        # Immediate diff + enqueue; indexing runs in the single worker (P3).
        # Explicit logging: paste the whole block when debugging empty syncs.
        log.info("sync: received footages=%d", len(body.footages))
        for f in body.footages[:10]:
            log.info(
                "sync: in path=%r size=%d mtime_ns=%d item_id=%d fps=%s",
                f.path, f.size, f.mtime_ns, f.item_id, f.frame_rate,
            )
        if len(body.footages) > 10:
            log.info("sync: ... +%d more", len(body.footages) - 10)
        registry = registry_module.load_registry()
        log.info("sync: registry entries=%d keys=%s", len(registry), sorted(registry)[:10])
        result = registry_module.diff(body.footages, registry)
        log.info(
            "sync: diff added=%s changed=%s removed=%s unchanged=%s pending=%s",
            result["added"], result["changed"], result["removed"],
            result["unchanged"], result["pending"],
        )
        from . import entitlements as entitlements_module

        allowed, code, message = entitlements_module.check_new_work(
            result["added"], result["changed"], result["unchanged"],
            registry, settings.plan,
        )
        if not allowed:
            log.info("sync: quota deny plan=%s (%s)", settings.plan, message)
            return JSONResponse(  # type: ignore[return-value]
                status_code=403,
                content=ErrorEnvelope(
                    error=ErrorBody(code=code, message=message)
                ).model_dump(),
            )
        registry_module.apply_sync(body.footages, result, registry)
        registry_module.save_registry(registry)
        # One active job per footage: a second enqueue for a key that already
        # has a live job reuses it (transient stat flips and Retry-spam must
        # never mint duplicate full pipeline runs).
        job_ids = []
        for key in result["added"] + result["changed"]:
            live = jobs_module.jobs.active_job_for(key)
            job_ids.append(live if live is not None else jobs_module.jobs.enqueue(key))
        log.info(
            "sync: +%d ~%d -%d =%d jobs=%d job_ids=%s",
            len(result["added"]),
            len(result["changed"]),
            len(result["removed"]),
            len(result["unchanged"]),
            len(job_ids),
            job_ids,
        )
        # Every job hands off to the engine (upload unless its content is already there).
        uploads = list(job_ids)
        return SyncResponse(
            added=result["added"],
            changed=result["changed"],
            removed=result["removed"],
            unchanged=result["unchanged"],
            pending=result["pending"],
            jobs=job_ids,
            uploads=uploads,
        )

    @app.get("/jobs/{job_id}", response_model=JobStatus)
    def job_status(job_id: str) -> JobStatus:
        job = jobs_module.jobs.get(job_id)
        if job is None:
            log.info("jobs: id=%s -> 404 NOT_FOUND", job_id)
            return JSONResponse(  # type: ignore[return-value]
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown job")
                ).model_dump(),
            )
        st = job.to_status()
        log.info(
            "jobs: id=%s footage=%s state=%s stages=%s",
            job_id, st.get("footage_key"), st.get("state"),
            [(s.get("name"), s.get("state"), s.get("done"), s.get("total")) for s in st.get("stages", [])],
        )
        return JobStatus(**st)

    @app.get("/host/{name}.jsx")
    def host_source(name: str):  # type: ignore[no-untyped-def]
        # Loader fallback for environments where CEP skips manifest ScriptPath
        # evaluation (panel UI loads, host functions stay undefined). Serves the
        # repo files VERBATIM — single source of truth stays panel/host/*.jsx;
        # the panel evalScripts the text only when its boot probes fail.
        # No shared JS modules across the bridge (AGENTS.md §2.3); the contract
        # still lives in docs/api.md. Never cachable — panel must get fresh code.
        import re

        from fastapi.responses import PlainTextResponse

        sources = {"json2": "json2.js", "host": "host.jsx"}
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or name not in sources:
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown host file")
                ).model_dump(),
            )
        from pathlib import Path as _Path

        host_dir = _Path(__file__).resolve().parents[2] / "panel" / "host"
        path = host_dir / sources[name]
        if not path.is_file():
            log.warning("host source missing: %s", path)
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="host file not on disk")
                ).model_dump(),
            )
        log.info("host: serving %s (%d bytes)", name, path.stat().st_size)
        return PlainTextResponse(
            path.read_text(encoding="utf-8"),
            media_type="text/plain",
            headers={"Cache-Control": "no-store"},
        )

    def _enqueue_retry(key: str) -> JobRetryResponse:
        # Idempotent: an explicit retry while a live job exists for the key
        # returns that job instead of stacking a duplicate run.
        live = jobs_module.jobs.active_job_for(key)
        if live is not None:
            log.info("retry: footage %s already active as %s; reusing", key, live)
            return JobRetryResponse(job_id=live, footage_key=key)
        registry = registry_module.load_registry()
        entry = registry.get(key)
        if entry is not None:
            entry["state"] = "indexing"
            entry.pop("error", None)
            registry_module.save_registry(registry)
        new_id = jobs_module.jobs.enqueue(key)
        return JobRetryResponse(job_id=new_id, footage_key=key)

    @app.post("/jobs/{job_id}/retry", response_model=JobRetryResponse)
    def job_retry(job_id: str):  # type: ignore[no-untyped-def]
        # Explicit re-enqueue of a failed job's footage (one click = one job;
        # reuses the live job when one already exists for the footage).
        # Auto-sync never re-enqueues (would hot-loop every 2s); only explicit
        # retry turns an `error`/orphaned entry back into `indexing` + a job.
        job = jobs_module.jobs.get(job_id)
        if job is None:
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown job")
                ).model_dump(),
            )
        resp = _enqueue_retry(job.footage_key)
        log.info("retry: job %s (footage %s) -> new job %s", job_id, job.footage_key, resp.job_id)
        return resp

    @app.post("/jobs/{job_id}/cancel", response_model=JobStatus)
    def job_cancel(job_id: str):  # type: ignore[no-untyped-def]
        # Drop a job that hasn't started yet. Running jobs (local or
        # backend-backed) can't be stopped mid-thread: 409 names the state,
        # and completion stays valid. Cancelled jobs leave polling on their
        # own (the panel drops unknown terminal states from its poll set).
        outcome = jobs_module.jobs.cancel(job_id)
        if outcome == "missing":
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown job")
                ).model_dump(),
            )
        if outcome != "cancelled":
            return JSONResponse(  # type: ignore[return-value]
                status_code=409,
                content=ErrorEnvelope(
                    error=ErrorBody(
                        code="NOT_CANCELLABLE",
                        message=f"job is {outcome}; only queued jobs can be cancelled",
                    )
                ).model_dump(),
            )
        job = jobs_module.jobs.get(job_id)
        log.info("cancel: job %s (footage %s)", job_id, job.footage_key)
        return JobStatus(**job.to_status())

    @app.post("/footage/{footage_key}/retry", response_model=JobRetryResponse)
    def footage_retry(footage_key: str):  # type: ignore[no-untyped-def]
        # Same as job retry, addressed by footage key — covers orphaned
        # entries (service restarted, panel reloaded, job id lost) and lets
        # the panel offer Retry/Resume straight from the footage list.
        import re as _re

        if not _re.fullmatch(r"[A-Za-z0-9_-]{1,64}", footage_key):
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown footage")
                ).model_dump(),
            )
        registry = registry_module.load_registry()
        if footage_key not in registry:
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown footage")
                ).model_dump(),
            )
        resp = _enqueue_retry(footage_key)
        log.info("retry: footage %s -> new job %s", footage_key, resp.job_id)
        return resp

    @app.get("/footage", response_model=list[FootageInfo])
    def footage() -> list[FootageInfo]:
        registry = registry_module.load_registry()
        log.info(
            "footage: entries=%d %s",
            len(registry),
            [(k, v.get("state"), v.get("path", "")[:80]) for k, v in list(registry.items())[:10]],
        )
        # Stable order: registry insertion order.
        return [
            FootageInfo(
                footage_key=key,
                path=entry.get("path", ""),
                content_id=entry.get("content_id", ""),
                shot_count=entry.get("shot_count", 0),
                duration_s=entry.get("duration_s", 0.0),
                indexed_at=entry.get("indexed_at"),
                state=entry.get("state", "indexing"),
                reused=bool(entry.get("reused", False)),
            )
            for key, entry in registry.items()
        ]

    @app.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(min_length=1),
        top_k: int = Query(default=9, ge=1, le=50),
        footage_keys: str | None = Query(default=None),
    ) -> SearchResponse:
        t0 = time.perf_counter()
        registry = registry_module.load_registry()
        wanted = set(footage_keys.split(",")) if footage_keys else None
        # content id -> first ready footage (registry order) holding those bytes: the
        # engine only knows content, the registry is the path authority (F5 insert).
        owners: dict[str, tuple[str, str]] = {}
        for key, entry in registry.items():
            cid = entry.get("content_id")
            if entry.get("state") == "ready" and cid and (wanted is None or key in wanted):
                owners.setdefault(cid, (key, entry.get("path", "")))
        log.info("search: q=%r top_k=%d footage_keys=%r contents=%d", q, top_k, footage_keys, len(owners))
        if not owners:
            return SearchResponse(query=q, took_ms=int((time.perf_counter() - t0) * 1000))
        provider = get_provider(settings)
        if provider is None:
            return _backend_error(None, "engine not configured")  # type: ignore[return-value]
        reply = provider.search(q, top_k, list(owners))
        if not reply.ok:
            log.info("search: engine fail code=%s status=%s %s", reply.code, reply.status, reply.message)
            return _backend_error(reply.transport_code, "engine search failed")  # type: ignore[return-value]
        results = []
        for r in reply.body.get("results", []):
            owner = owners.get(r.get("content_id", ""))
            if owner is None:
                continue
            results.append(SearchResult(**{**r, "footage_key": owner[0], "source_path": owner[1]}))
        log.info("search: results=%d engine_ms=%s", len(results), reply.body.get("took_ms"))
        return SearchResponse(query=q, took_ms=int((time.perf_counter() - t0) * 1000),
                              entities=reply.body.get("entities", []), results=results)

    @app.get("/thumb/{footage_key}/{shot_id}.jpg")
    def thumb(footage_key: str, shot_id: int):  # type: ignore[no-untyped-def]
        not_found = _error(404, "NOT_FOUND", "unknown thumbnail")
        if not KEY_RE.fullmatch(footage_key) or shot_id < 0:
            return not_found
        cid = registry_module.load_registry().get(footage_key, {}).get("content_id")
        # content_id comes from registry.json, not from the request — but that
        # file is plain unauthenticated JSON on disk, and registry.thumbs_dir()
        # concatenates it into a path. Validate it here so no future writer (a
        # prune route, a sync client, another tool) can turn this route into an
        # arbitrary file read. Same predicate the engine uses.
        if not cid or not CONTENT_ID_RE.fullmatch(cid):
            return not_found
        path = registry_module.thumbs_dir(cid) / f"{shot_id}.jpg"
        if path.is_file():
            # Thumbnails over HTTP (never file://) — avoids CEF file-access flags (D6).
            return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": THUMB_CACHE})
        # Not synced down yet (sync failed or still running): fetch once, cache by content.
        provider = get_provider(settings)
        if provider is None:
            return not_found
        reply = provider.thumb_bytes(cid, shot_id)
        if reply.ok and reply.body:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(reply.body)
            except OSError:
                pass
            return Response(content=reply.body, media_type="image/jpeg", headers={"Cache-Control": THUMB_CACHE})
        if reply.code in (ASLEEP, TIMEOUT):
            return _backend_error(reply.code, "engine thumb failed")
        return not_found

    @app.exception_handler(Exception)
    async def unhandled(request, exc: Exception):  # type: ignore[no-untyped-def]
        log.exception("unhandled error: %s", exc)
        return _error(500, "INTERNAL", "internal error")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "tempo_service.app:app",
        host="127.0.0.1",  # local only — never expose on LAN
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
