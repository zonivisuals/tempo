"""FastAPI wiring (AGENTS.md §2.2, §3.1).

Lifespan wires the registry/worker only — model weights are loaded lazily
per pipeline stage (AGENTS.md D8: single 8–12GB GPU cannot hold all
weights resident) and reported via /health `models_loaded`.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from . import drive as drive_module
from . import jobs as jobs_module
from . import registry as registry_module
from . import search as search_module
from .backends import get_provider
from .config import settings
from .indexer.models import MODELS_LOADED as models_loaded
from .schemas import (
    AuthLoginRequest,
    AuthMeResponse,
    AuthSessionResponse,
    AuthSignupRequest,
    BackendStatus,
    Contributions,
    DriveAuthRequest,
    ErrorBody,
    ErrorEnvelope,
    FootageInfo,
    HealthResponse,
    JobRetryResponse,
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
        "tempo startup: artifact_root=%s format_version=%d auth_mode=%s",
        settings.artifact_root,
        settings.format_version,
        settings.auth_mode,
    )
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    from .proxy import register as register_proxy

    register_proxy()  # backend handoff when configured, else local pipeline
    yield
    log.info("tempo shutdown")


def create_app() -> FastAPI:
    from . import auth as auth_module

    app = FastAPI(title="Tempo", lifespan=lifespan)
    auth_client = auth_module.AuthClient(settings.auth_url, settings.auth_timeout_s)
    token_store = auth_module.TokenStore(backend=settings.token_store)

    def _bearer(request) -> str | None:  # type: ignore[no-untyped-def]
        raw = request.headers.get("authorization", "")
        if raw[:7].lower() == "bearer ":
            return raw[7:].strip() or None
        return None

    def _user(request):  # type: ignore[no-untyped-def]
        """Identity for protected routes. 401 AUTH_REQUIRED when auth_mode
        is on and neither the request token nor the stored session validates.
        Localhost-only sidecar serving one editor; the production gateway
        re-enforces per request (ADR-0005)."""
        if settings.auth_mode != "on":
            return {"user_id": "local", "email": ""}
        ident = auth_module.current_user(_bearer(request), auth_client, token_store)
        if ident is None:
            return JSONResponse(
                status_code=401,
                content=ErrorEnvelope(
                    error=ErrorBody(code="AUTH_REQUIRED", message="sign in first")
                ).model_dump(),
            )
        return ident

    @app.post("/auth/signup", response_model=AuthSessionResponse)
    def auth_signup(body: AuthSignupRequest):  # type: ignore[no-untyped-def]
        try:
            token, user = auth_client.sign_up(body.name, body.email, body.password)
        except auth_module.AuthError as exc:
            log.info("auth signup rejected (%s)", exc)
            return JSONResponse(
                status_code=401,
                content=ErrorEnvelope(
                    error=ErrorBody(code="AUTH_REJECTED", message="sign-up rejected")
                ).model_dump(),
            )
        ident = auth_client.validate(token) or {"expires_at": 0.0}
        token_store.save(token, user["user_id"], user["email"], ident.get("expires_at", 0.0))
        log.info("auth signup ok user=%s", user["user_id"])
        return AuthSessionResponse(user_id=user["user_id"], email=user["email"])

    @app.post("/auth/login", response_model=AuthSessionResponse)
    def auth_login(body: AuthLoginRequest):  # type: ignore[no-untyped-def]
        try:
            token, user = auth_client.sign_in(body.email, body.password)
        except auth_module.AuthError as exc:
            log.info("auth login rejected (%s)", exc)
            return JSONResponse(
                status_code=401,
                content=ErrorEnvelope(
                    error=ErrorBody(code="AUTH_REJECTED", message="sign-in rejected")
                ).model_dump(),
            )
        ident = auth_client.validate(token) or {"expires_at": 0.0}
        token_store.save(token, user["user_id"], user["email"], ident.get("expires_at", 0.0))
        log.info("auth login ok user=%s", user["user_id"])
        return AuthSessionResponse(user_id=user["user_id"], email=user["email"])

    @app.post("/auth/logout")
    def auth_logout(request: Request):  # type: ignore[no-untyped-def]
        token = _bearer(request)
        saved = token_store.load()
        auth_client.drop(token or (saved or {}).get("token", ""))
        token_store.clear()
        return {"ok": True}

    @app.get("/auth/me", response_model=AuthMeResponse)
    def auth_me(request: Request):  # type: ignore[no-untyped-def]
        if settings.auth_mode != "on":
            return AuthMeResponse(logged_in=True, user_id="local", email="")
        ident = auth_module.current_user(_bearer(request), auth_client, token_store)
        if ident is None:
            return AuthMeResponse(logged_in=False)
        return AuthMeResponse(logged_in=True, user_id=ident["user_id"], email=ident["email"])

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        provider = get_provider(
            settings.backend, settings.backend_url, settings.backend_token,
            settings.backend_health_timeout_s,
        )
        probe = provider.health() if provider else {"reachable": False, "gpu": False}
        return HealthResponse(
            status="ok",
            models_loaded=dict(models_loaded),
            artifact_root=str(settings.artifact_root),
            backend=BackendStatus(reachable=probe["reachable"], gpu=probe["gpu"]),
        )

    @app.post("/drive-auth")
    def drive_auth(body: DriveAuthRequest):  # type: ignore[no-untyped-def]
        # OAuth bootstrap lands with the storage provider upload flow (P2).
        # Honest stub — never a silent stall (re-auth hint).
        log.info("drive-auth requested (code len=%d)", len(body.code))
        return JSONResponse(
            status_code=501,
            content=ErrorEnvelope(
                error=ErrorBody(
                    code="DRIVE_NOT_CONFIGURED",
                    message="Direct upload not configured yet; copy to storage manually",
                )
            ).model_dump(),
        )

    @app.post("/sync", response_model=SyncResponse)
    def sync(request: Request, body: SyncRequest) -> SyncResponse:
        maybe = _user(request)
        if isinstance(maybe, JSONResponse):
            return maybe  # type: ignore[return-value]
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
            "sync: diff added=%s changed=%s removed=%s unchanged=%s",
            result["added"], result["changed"], result["removed"], result["unchanged"],
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
        job_ids = [
            jobs_module.jobs.enqueue(key) for key in result["added"] + result["changed"]
        ]
        provider = get_provider(
            settings.backend, settings.backend_url, settings.backend_token,
            settings.backend_timeout_s,
        )
        log.info(
            "sync: +%d ~%d -%d =%d jobs=%d job_ids=%s uploads_pending=%s",
            len(result["added"]),
            len(result["changed"]),
            len(result["removed"]),
            len(result["unchanged"]),
            len(job_ids),
            job_ids,
            bool(provider),
        )
        uploads = list(job_ids) if provider else []
        return SyncResponse(
            added=result["added"],
            changed=result["changed"],
            removed=result["removed"],
            unchanged=result["unchanged"],
            jobs=job_ids,
            uploads=uploads,
        )

    @app.get("/jobs/{job_id}", response_model=JobStatus)
    def job_status(request: Request, job_id: str) -> JobStatus:
        maybe = _user(request)
        if isinstance(maybe, JSONResponse):
            return maybe  # type: ignore[return-value]
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
        registry = registry_module.load_registry()
        entry = registry.get(key)
        if entry is not None:
            entry["state"] = "indexing"
            entry.pop("error", None)
            registry_module.save_registry(registry)
        new_id = jobs_module.jobs.enqueue(key)
        return JobRetryResponse(job_id=new_id, footage_key=key)

    @app.post("/jobs/{job_id}/retry", response_model=JobRetryResponse)
    def job_retry(request: Request, job_id: str):  # type: ignore[no-untyped-def]
        # Explicit re-enqueue of a failed job's footage (one click = one job).
        # Auto-sync never re-enqueues (would hot-loop every 2s); only explicit
        # retry turns an `error`/orphaned entry back into `indexing` + a job.
        maybe = _user(request)
        if isinstance(maybe, JSONResponse):
            return maybe
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

    @app.post("/footage/{footage_key}/retry", response_model=JobRetryResponse)
    def footage_retry(request: Request, footage_key: str):  # type: ignore[no-untyped-def]
        # Same as job retry, addressed by footage key — covers orphaned
        # entries (service restarted, panel reloaded, job id lost) and lets
        # the panel offer Retry/Resume straight from the footage list.
        maybe = _user(request)
        if isinstance(maybe, JSONResponse):
            return maybe
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
        # Stable order: registry insertion order (search matrices rely on it).
        return [
            FootageInfo(
                footage_key=key,
                path=entry.get("path", ""),
                drive_path=entry.get(
                    "drive_path",
                    drive_module.drive_path_for(key, entry.get("path", "")),
                ),
                shot_count=entry.get("shot_count", 0),
                duration_s=entry.get("duration_s", 0.0),
                indexed_at=entry.get("indexed_at"),
                state=entry.get("state", "indexing"),
            )
            for key, entry in registry.items()
        ]

    @app.get("/search", response_model=SearchResponse)
    def search(
        request: Request,
        q: str = Query(min_length=1),
        top_k: int = Query(default=8, ge=1, le=50),
        footage_keys: str | None = Query(default=None),
    ) -> SearchResponse:
        import time

        maybe = _user(request)
        if isinstance(maybe, JSONResponse):
            return maybe  # type: ignore[return-value]
        t0 = time.perf_counter()
        provider = get_provider(
            settings.backend, settings.backend_url, settings.backend_token,
            settings.backend_timeout_s,
        )
        log.info("search: q=%r top_k=%d footage_keys=%r backend=%s", q, top_k, footage_keys,
                 bool(provider))
        if provider:
            ok, status, body, code = provider.search(q, top_k, footage_keys)
            if ok and body is not None:
                try:
                    resp = SearchResponse(**body)
                except Exception as exc:
                    log.warning("search: backend body invalid (%s) body=%r", exc, str(body)[:500])
                    raise
                # The backend never knows the editor's local disk path (it indexes
                # storage copies) — the registry is the path authority. Backfill
                # empty source_path so result-click can locate/import (F5);
                # scoring/ordering untouched (backend remains authoritative).
                _reg = registry_module.load_registry()
                _filled = 0
                for _r in resp.results:
                    if not _r.source_path:
                        _p = _reg.get(_r.footage_key, {}).get("path", "")
                        if _p:
                            _r.source_path = _p
                            _filled += 1
                if _filled:
                    log.info("search: backfilled source_path for %d results", _filled)
                log.info("search: backend ok results=%d took_ms=%s", len(resp.results), body.get("took_ms"))
                return resp
            err_status = 504 if code == "BACKEND_TIMEOUT" else 502
            log.info("search: backend fail code=%s status=%s", code, status)
            return JSONResponse(  # type: ignore[return-value]
                status_code=err_status,
                content=ErrorEnvelope(
                    error=ErrorBody(code=code or "BACKEND_UNREACHABLE", message="backend search failed")
                ).model_dump(),
            )
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
        if path.is_file():
            # Thumbnails over HTTP (never file://) — avoids CEF file-access flags.
            return FileResponse(
                path,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        # Backend-indexed footage: thumbs live remotely until synced down.
        # Proxy + cache locally so the panel stays instant after first hit.
        provider = get_provider(
            settings.backend, settings.backend_url, settings.backend_token,
            settings.backend_timeout_s,
        )
        if provider:
            from fastapi.responses import Response

            ok, data, code = provider.thumb_bytes(footage_key, shot_id)
            if ok and data:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                except OSError:
                    pass
                return Response(
                    content=data,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
            if code in ("BACKEND_ASLEEP", "BACKEND_TIMEOUT"):
                err_status = 504 if code == "BACKEND_TIMEOUT" else 502
                return JSONResponse(
                    status_code=err_status,
                    content=ErrorEnvelope(
                        error=ErrorBody(code=code, message="backend thumb failed")
                    ).model_dump(),
                )
        return JSONResponse(
            status_code=404,
            content=ErrorEnvelope(
                error=ErrorBody(code="NOT_FOUND", message="unknown thumbnail")
            ).model_dump(),
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
