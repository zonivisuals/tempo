"""Engine /v1 API (docs/engine-api.md, ADR-0008).

Bound to the instance's localhost and reached through `brev port-forward`;
every route except /v1/health requires the bearer token (fail closed when
none is configured). The app is built by `create_app()` — no import-time
side effects — and run with `python -m tempo_engine.app` or
`uvicorn tempo_engine.app:create_app --factory`.

Tests inject `runner` (fake pipeline) and `encoders` (fixed query vectors);
production uses `pipeline.build` and the model singletons.
"""

import hmac
import logging
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import numpy as np
from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from . import fingerprint, models, pipeline, search, textproc
from .config import EngineSettings, Profile, settings, weights
from .corpus import CorpusCache
from .jobs import EngineJobs, Runner
from .library import ContentMismatch, Library, OffsetMismatch
from .schemas import (
    ErrorBody,
    ErrorEnvelope,
    Health,
    IndexRequest,
    IndexResponse,
    Job,
    LibraryEntry,
    SearchResponse,
    SearchResult,
    UploadState,
)

log = logging.getLogger("tempo.engine")

THUMB_CACHE = "public, max-age=86400"
MB = 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _envelope(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content=ErrorEnvelope(error=ErrorBody(code=code, message=message)).model_dump())


@dataclass
class Encoders:
    visual: Callable[[str], np.ndarray]
    text: Callable[[str], np.ndarray]
    ner: Callable[[list[str]], list[list[str]]]


def default_encoders() -> Encoders:
    return Encoders(visual=lambda q: models.siglip_text_embeds([q])[0],
                    text=models.embed_query, ner=models.ner_batch)


def create_app(cfg: EngineSettings | None = None, runner: Runner | None = None,
               encoders: Encoders | None = None, prof: Profile | None = None) -> FastAPI:
    cfg = cfg or settings
    prof = prof or models.current_profile()
    signature = pipeline.current_signature(prof)
    library = Library(cfg.data_root)
    corpora = CorpusCache(cfg.corpus_cache_size)

    def build(cid: str, report: pipeline.Reporter) -> dict:
        return pipeline.build(cid, library.raw(cid), library.entry_dir(cid), report, prof)

    index_content = runner or build

    def run_job(cid: str, report: pipeline.Reporter) -> dict:
        summary = index_content(cid, report)
        # Retention (ADR-0006): raw bytes go once the index persists; the stage cache keeps
        # frames, so only a shots/transcribe rebuild would ever need them again.
        if cfg.raw_retention == "delete":
            library.purge_raw(cid)
        return summary

    jobs = EngineJobs(cfg.data_root, pipeline.STAGES, run_job)
    injected = encoders is not None
    enc = encoders or default_encoders()
    warm = {"state": "loading" if (cfg.preload_query_models and not injected) else "ready"}

    def preload() -> None:
        try:
            t0 = time.time()
            models.preload_query_models()
            warm["state"] = "ready"
            log.info("query models warm in %.1fs", time.time() - t0)
        except Exception as exc:
            warm["state"] = "error"
            log.exception("query model warm-up failed: %s", exc)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        log.info("engine startup: data_root=%s device=%s signature=%s", cfg.data_root, models.device(), signature)
        jobs.recover()
        jobs.start()
        if warm["state"] == "loading":
            threading.Thread(target=preload, daemon=True, name="tempo-engine-warmup").start()
        yield
        log.info("engine shutdown")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not cfg.token:
            raise ApiError(500, "NO_TOKEN", "engine token not configured")
        if not hmac.compare_digest(authorization or "", f"Bearer {cfg.token}"):
            raise ApiError(401, "UNAUTHORIZED", "bad token")

    def check_cid(cid: str) -> str:
        if not fingerprint.valid(cid):
            raise ApiError(404, "NOT_FOUND", "unknown content id")
        return cid

    def needs_upload(cid: str) -> bool:
        return library.raw(cid) is None and not pipeline.source_cached(cid, library.entry_dir(cid), prof)

    # docs_url/redoc_url/openapi_url are off: they sit on `app`, outside the
    # /v1 router's require_token dependency, so leaving them on publishes the
    # full route/parameter/model schema to anything that can reach the port.
    app = FastAPI(
        title="Tempo engine",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):  # type: ignore[no-untyped-def]
        return _envelope(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError):  # type: ignore[no-untyped-def]
        return _envelope(422, "BAD_REQUEST", str(exc.errors())[:500])

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):  # type: ignore[no-untyped-def]
        log.exception("unhandled error: %s", exc)
        return _envelope(500, "INTERNAL", "internal error")

    @app.get("/v1/health", response_model=Health)
    def health() -> Health:
        return Health(gpu=models.gpu(), device=models.device(), signature=signature,
                      stages=pipeline.STAGES, query_models=warm["state"])

    @v1.get("/library/{cid}", response_model=LibraryEntry)
    def library_entry(cid: str) -> LibraryEntry:
        check_cid(cid)
        up = library.upload_state(cid)
        base = dict(content_id=cid, needs_upload=needs_upload(cid), received=up["received"], size=up["size"])
        live = jobs.live_for(cid)
        if live:
            return LibraryEntry(state="indexing", job_id=live, **base)
        index_state = library.index_state(cid, signature)
        if index_state == "ready":
            meta = library.index_meta(cid)
            return LibraryEntry(state="ready", shot_count=int(meta.get("n_shots", 0)),
                                duration_s=float(meta.get("duration", 0.0)), fps=float(meta.get("fps", 0.0)),
                                **base)
        last = jobs.last_for(cid)
        if last and last["state"] == "error":
            return LibraryEntry(state="error", job_id=last["job_id"], error=last["error"], **base)
        if index_state == "stale":
            return LibraryEntry(state="stale", **base)
        if up["complete"]:
            return LibraryEntry(state="uploaded", **base)
        return LibraryEntry(state="partial" if up["received"] else "missing", **base)

    @v1.get("/uploads/{cid}", response_model=UploadState)
    def upload_state(cid: str) -> UploadState:
        return UploadState(**library.upload_state(check_cid(cid)))

    @v1.put("/uploads/{cid}", response_model=UploadState)
    async def upload_chunk(cid: str, request: Request, offset: int = Query(ge=0), size: int = Query(gt=0),
                           name: str = Query(default="")) -> UploadState:
        check_cid(cid)
        limit = cfg.max_chunk_mb * MB
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            raise ApiError(413, "CHUNK_TOO_LARGE", f"chunks are limited to {cfg.max_chunk_mb} MiB")
        data = await request.body()
        if len(data) > limit:
            raise ApiError(413, "CHUNK_TOO_LARGE", f"chunks are limited to {cfg.max_chunk_mb} MiB")
        try:
            state = await run_in_threadpool(library.append, cid, offset, size, name, data)
        except OffsetMismatch as exc:
            raise ApiError(409, "OFFSET_MISMATCH", f'{{"received": {exc.received}}}')
        except ContentMismatch as exc:
            raise ApiError(422, "CONTENT_MISMATCH", str(exc))
        return UploadState(**state)

    @v1.post("/index", response_model=IndexResponse)
    def index(body: IndexRequest) -> IndexResponse:
        cid = check_cid(body.content_id)
        live = jobs.live_for(cid)
        if live:
            job = jobs.get(live)
            return IndexResponse(job_id=live, state=job["state"] if job else "queued")
        if library.index_state(cid, signature) == "ready":
            return IndexResponse(job_id=None, state="done")
        if needs_upload(cid):
            raise ApiError(409, "SOURCE_MISSING", "upload the footage before indexing")
        job = jobs.submit(cid)
        return IndexResponse(job_id=job["job_id"], state=job["state"])

    @v1.get("/jobs/{job_id}", response_model=Job)
    def job_status(job_id: str) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise ApiError(404, "NOT_FOUND", "unknown job")
        return Job(**job)

    @v1.get("/search", response_model=SearchResponse)
    def do_search(q: str = Query(min_length=1), top_k: int = Query(default=8, ge=1, le=50),
                  content_ids: str | None = Query(default=None)) -> SearchResponse:
        t0 = time.perf_counter()
        if warm["state"] == "loading":
            raise ApiError(503, "MODEL_WARMING", "query models are loading")
        if warm["state"] == "error":
            raise ApiError(503, "MODEL_NOT_LOADED", "query models failed to load")
        wanted = [c for c in content_ids.split(",") if c] if content_ids else library.ready_ids(signature)
        ready = [c for c in wanted if fingerprint.valid(c) and library.index_state(c, signature) == "ready"]
        if not ready:
            return SearchResponse(query=q, took_ms=int((time.perf_counter() - t0) * 1000))
        corpus = corpora.get([library.entry_dir(c) for c in ready])
        try:
            q_ents = textproc.query_entities(q, corpus.vocab, enc.ner)
            qv, qt = enc.visual(q), enc.text(q)
        except (ImportError, OSError) as exc:
            log.warning("query encoding unavailable (%s)", exc)
            raise ApiError(503, "MODEL_NOT_LOADED", "query models not available")
        q_tokens = textproc.tokenize(q) + [t for e in q_ents for t in textproc.tokenize(corpus.vocab.get(e, e))]
        hits = search.rank(corpus, qv, qt, q_ents, q_tokens, weights(cfg), cfg.zscore_cap,
                           cfg.faiss_candidates, top_k, cfg.dedupe_scenes)
        results = []
        for h in hits:
            ix, s = corpus.shot(h.row)
            results.append(SearchResult(
                content_id=ix.content_id, shot_id=int(s["shot_id"]), scene_id=int(s["scene_id"]),
                start_s=float(s["start_time"]), end_s=float(s["end_time"]), score=h.score,
                contributions=h.contributions, raw_cos=h.raw_cos, transcript=s["transcript"],
                dialogue=s["dialogue_en"], caption=s["caption"], ocr=s["ocr_text"],
                entities=s["entities"], emotions=s["emotions"]))
        took = int((time.perf_counter() - t0) * 1000)
        log.info("search q=%r shots=%d results=%d took_ms=%d", q, corpus.n, len(results), took)
        return SearchResponse(query=q, took_ms=took, entities=[corpus.vocab.get(e, e) for e in q_ents],
                              results=results)

    @v1.get("/library/{cid}/thumbs/{shot_id}.jpg")
    def thumb(cid: str, shot_id: int):  # type: ignore[no-untyped-def]
        path = library.thumb(check_cid(cid), shot_id)
        if shot_id < 0 or not path.is_file():
            raise ApiError(404, "NOT_FOUND", "unknown thumbnail")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": THUMB_CACHE})

    @v1.get("/library/{cid}/thumbs.tar")
    def thumbs_tar(cid: str):  # type: ignore[no-untyped-def]
        if library.index_state(check_cid(cid), signature) != "ready":
            raise ApiError(404, "NOT_FOUND", "content not indexed")
        return FileResponse(library.thumbs_tar(cid), media_type="application/x-tar")

    app.include_router(v1)
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=settings.log_level)
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
