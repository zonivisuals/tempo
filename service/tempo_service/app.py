"""FastAPI wiring (AGENTS.md §2.2, §3.1).

Lifespan wires the registry/worker only — model weights are loaded lazily
per pipeline stage (AGENTS.md D8: single 8–12GB GPU cannot hold all
weights resident) and reported via /health `models_loaded`.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import jobs as jobs_module
from . import registry as registry_module
from .config import settings
from .schemas import (
    ErrorBody,
    ErrorEnvelope,
    FootageInfo,
    HealthResponse,
    JobStatus,
    SyncRequest,
    SyncResponse,
)

log = logging.getLogger("tempo")
logging.basicConfig(level=settings.log_level)

# Lazily-loaded model singletons live here (populated by indexer stages,
# never all at once on a single consumer GPU). P1 only declares the slots.
models_loaded: dict[str, bool] = {
    "clip": False,
    "whisper": False,
    "easyocr": False,
    "blip2": False,
    "ner": False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Official FastAPI lifespan pattern: setup before yield, cleanup after.
    # https://fastapi.tiangolo.com/advanced/events/
    log.info(
        "tempo startup: artifact_root=%s format_version=%d",
        settings.artifact_root,
        settings.format_version,
    )
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    yield
    log.info("tempo shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Tempo", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            models_loaded=dict(models_loaded),
            artifact_root=str(settings.artifact_root),
        )

    @app.post("/sync", response_model=SyncResponse)
    def sync(body: SyncRequest) -> SyncResponse:
        # Immediate diff + enqueue; indexing runs in the single worker (P3).
        registry = registry_module.load_registry()
        result = registry_module.diff(body.footages, registry)
        registry_module.apply_sync(body.footages, result, registry)
        registry_module.save_registry(registry)
        job_ids = [
            jobs_module.jobs.enqueue(key) for key in result["added"] + result["changed"]
        ]
        log.info(
            "sync: +%d ~%d -%d =%d jobs=%d",
            len(result["added"]),
            len(result["changed"]),
            len(result["removed"]),
            len(result["unchanged"]),
            len(job_ids),
        )
        return SyncResponse(
            added=result["added"],
            changed=result["changed"],
            removed=result["removed"],
            unchanged=result["unchanged"],
            jobs=job_ids,
        )

    @app.get("/jobs/{job_id}", response_model=JobStatus)
    def job_status(job_id: str) -> JobStatus:
        job = jobs_module.jobs.get(job_id)
        if job is None:
            return JSONResponse(  # type: ignore[return-value]
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown job")
                ).model_dump(),
            )
        return JobStatus(**job.to_status())

    @app.get("/footage", response_model=list[FootageInfo])
    def footage() -> list[FootageInfo]:
        registry = registry_module.load_registry()
        # Stable order: registry insertion order (search matrices rely on it).
        return [
            FootageInfo(
                footage_key=key,
                path=entry.get("path", ""),
                shot_count=entry.get("shot_count", 0),
                duration_s=entry.get("duration_s", 0.0),
                indexed_at=entry.get("indexed_at"),
                state=entry.get("state", "indexing"),
            )
            for key, entry in registry.items()
        ]

    @app.exception_handler(Exception)
    async def unhandled(request, exc: Exception):  # type: ignore[no-untyped-def]
        log.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ErrorEnvelope(
                error=ErrorBody(code="INTERNAL", message="internal error")
            ).model_dump(),
        )

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
