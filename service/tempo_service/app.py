"""FastAPI wiring (AGENTS.md §2.2, §3.1).

Lifespan wires the registry/worker only — model weights are loaded lazily
per pipeline stage (AGENTS.md D8: single 8–12GB GPU cannot hold all
weights resident) and reported via /health `models_loaded`.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

from . import jobs as jobs_module
from . import registry as registry_module
from . import search as search_module
from .config import settings
from .indexer.models import MODELS_LOADED as models_loaded
from .schemas import (
    Contributions,
    ErrorBody,
    ErrorEnvelope,
    FootageInfo,
    HealthResponse,
    JobStatus,
    RawCos,
    SearchResponse,
    SearchResult,
    SyncRequest,
    SyncResponse,
)

log = logging.getLogger("tempo")
logging.basicConfig(level=settings.log_level)


def _ms(t0: float) -> int:
    import time

    return int((time.perf_counter() - t0) * 1000)


def _require_cached(repo_id: str) -> None:
    """Raise OSError unless the model weights are already on disk.

    `local_files_only` performs a pure cache probe — no network, never a
    download. /search must never trigger model downloads (§3.4).
    """
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, local_files_only=True)


def _query_text_model():  # type: ignore[no-untyped-def]
    """CLIP text encoder from local cache only; raises OSError when absent."""
    import torch
    from transformers import CLIPProcessor, CLIPTextModelWithProjection

    from .indexer.models import load

    _require_cached(settings.clip_model_name)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    def factory():  # type: ignore[no-untyped-def]
        text_model = CLIPTextModelWithProjection.from_pretrained(settings.clip_model_name)
        text_model.to(device)  # type: ignore[arg-type]  # stubs mistype Module.to
        text_model.eval()
        return (
            text_model,
            CLIPProcessor.from_pretrained(settings.clip_model_name),
            device,
        )

    return cast("tuple[Any, Any, str]", load("clip_text", factory))


def _query_entities_cached(query: str) -> list[str]:
    """Query entities via the shared extractor; [] when NER isn't cached.

    Unlike the text model (503), a missing NER is honest degradation: the
    anchor/entity contributions show 0.0 instead of blocking search.
    """
    from .indexer import ner as ner_module

    try:
        _require_cached(settings.ner_model_name)
    except Exception as exc:
        log.info("search without cached NER (%s); entities=[]", exc)
        return []
    try:
        return ner_module.extract_entities(query)
    except Exception as exc:
        log.info("NER extract failed (%s); entities=[]", exc)
        return []


def _embed_query(model, processor, device: str, query: str):  # type: ignore[no-untyped-def]
    import torch

    inputs = processor(text=[query], return_tensors="pt", padding=True, truncation=True).to(
        device
    )
    with torch.no_grad():
        emb = model(**inputs).text_embeds
    emb = emb / emb.norm(p=2, dim=-1, keepdim=True)
    return emb.cpu().numpy().astype("float32")[0]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Official FastAPI lifespan pattern: setup before yield, cleanup after.
    # https://fastapi.tiangolo.com/advanced/events/
    # Registry/worker wiring only — model weights stay lazy per stage (D8).
    log.info(
        "tempo startup: artifact_root=%s format_version=%d",
        settings.artifact_root,
        settings.format_version,
    )
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    from .indexer.pipeline import register as register_pipeline

    register_pipeline()
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

    @app.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(min_length=1),
        top_k: int = Query(default=8, ge=1, le=50),
        footage_keys: str | None = Query(default=None),
    ) -> SearchResponse:
        import time

        t0 = time.perf_counter()
        registry = registry_module.load_registry()
        keys = footage_keys.split(",") if footage_keys else None
        corpus = search_module.load_corpus(
            settings.artifact_root, registry, keys, q.lower().split()
        )
        shots = corpus["shots"]
        if not shots:
            return SearchResponse(query=q, took_ms=_ms(t0), results=[])

        try:
            model, processor, device = _query_text_model()
        except Exception as exc:
            log.warning("search without cached text model (%s)", exc)
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content=ErrorEnvelope(
                    error=ErrorBody(code="MODEL_NOT_LOADED", message="text model not loaded")
                ).model_dump(),
            )
        query_entities = _query_entities_cached(q)
        q_emb = _embed_query(model, processor, device, q)

        out = search_module.score_query(
            q_emb,
            corpus["visual"],
            corpus["dialogue"],
            corpus["caption"],
            corpus["bm25_raw"],
            query_entities,
            [s["entities"] for s in shots],
            [s["text_context"] for s in shots],
            settings.dense_w,
            settings.bm25_w,
            settings.anchor_w,
            settings.entity_boost,
        )
        top = __import__("numpy").argsort(-out["final"], kind="stable")[:top_k]
        results = []
        for idx in top:
            s = shots[int(idx)]
            wk = search_module.KEY_NAMES[int(out["winner"][idx])]
            results.append(
                SearchResult(
                    footage_key=s["footage_key"],
                    shot_id=s["shot_id"],
                    source_path=s["source_path"],
                    start_s=s["start_s"],
                    end_s=s["end_s"],
                    score=float(out["final"][idx]),
                    winning_key=wk,
                    raw_cos=RawCos(
                        visual=float(out["key_stack"][0, idx]),
                        dialogue=float(out["key_stack"][1, idx]),
                        caption=float(out["key_stack"][2, idx]),
                    ),
                    contributions=Contributions(
                        dense=float(out["dense_c"][idx]),
                        bm25=float(out["bm25_c"][idx]),
                        anchor=float(out["anchor_c"][idx]),
                        entity_boost=float(out["boost"][idx]),
                    ),
                    transcript=s["transcript"],
                    caption=s["caption"],
                    entities=s["entities"],
                )
            )
        return SearchResponse(query=q, took_ms=_ms(t0), results=results)

    @app.get("/thumb/{footage_key}/{shot_id}.jpg")
    def thumb(footage_key: str, shot_id: int):  # type: ignore[no-untyped-def]
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", footage_key) or shot_id < 0:
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown thumbnail")
                ).model_dump(),
            )
        path = (
            settings.artifact_root / "footage" / footage_key / "thumbs" / f"shot_{shot_id}.jpg"
        )
        if not path.is_file():
            return JSONResponse(
                status_code=404,
                content=ErrorEnvelope(
                    error=ErrorBody(code="NOT_FOUND", message="unknown thumbnail")
                ).model_dump(),
            )
        # Thumbnails over HTTP (never file://) — avoids CEF file-access flags.
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
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
