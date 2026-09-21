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

from .config import settings
from .schemas import ErrorBody, ErrorEnvelope, HealthResponse

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
