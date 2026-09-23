"""FastAPI contract app for the Modal backend (ADR-0004).

Speaks the docs/api.md backend subset: GET /health, POST /index,
GET /jobs/{id}, GET /search, GET /thumb/{key}/{id}.jpg. No `modal` import
here — this module is plain FastAPI + numpy and unit-testable on CPU. The
Modal wiring (volumes, secrets, GPU, ASGI mount) lives in modal_app.py.

Auth: per-deploy bearer token from env (Modal Secret in production), the
entire auth model. Never logged.

State: jobs + footage index live in memory; per-stage checkpoints persist
as JSON under checkpoint_root (a Modal Volume mount in production, tmp in
tests), so preemption resumes instead of restarting.
"""

import json
import logging
import os
import pickle
import queue
import threading
import uuid
from pathlib import Path

log = logging.getLogger("tempo.modal_api")

STAGES = [
    "upload",
    "shots",
    "visual_embed",
    "cluster",
    "transcribe",
    "ocr",
    "captions",
    "text_embed",
    "ner",
    "build_index",
]


def _blank_stages():
    return {n: {"name": n, "state": "pending", "done": 0, "total": 0} for n in STAGES}


def ingress_resolver(mount):
    """Build a resolve_source mapping storage refs under a volume mount.

    drive_path arrives as tempo/<key>/<basename> and the leading folder is
    part of the on-volume layout (no stripping). Absolute paths and `..`
    segments are rejected (fail closed — a malicious ref must never escape
    the mount).
    """

    def resolve(drive_path):
        from pathlib import Path as _Path
        from pathlib import PurePosixPath

        rel = PurePosixPath(drive_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"unsafe storage ref: {drive_path!r}")
        return _Path(mount) / rel.as_posix()

    return resolve


def create_app(*, auth_token, artifacts_root, checkpoint_root, run_all=None,
               embed_query=None, resolve_source=None):
    """Build the FastAPI app.

    run_all: fn(src_path, out_dir, progress) — defaults to pipeline.run_all
        (GPU); tests inject a fake writing fixture artifacts.
    embed_query: fn(text) -> L2-normalized np vector — defaults to None,
        meaning the CLIP text singleton (GPU). Tests inject a fixed vector.
        Missing model on CPU hosts → 503 MODEL_NOT_LOADED (same honest code).
    resolve_source: fn(drive_path) -> Path mapping a storage ref to a local
        file — defaults to identity; the Modal deploy maps refs into the
        ingress Volume. Missing file → job error naming the location.
    """
    from fastapi import FastAPI, Header, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel

    from . import pipeline as pipeline_module
    from . import scoring as scoring_module

    artifacts_root = Path(artifacts_root)
    checkpoint_root = Path(checkpoint_root)
    run_all = run_all or pipeline_module.run_all
    resolve_source = resolve_source or (lambda ref: Path(ref))

    class IndexReq(BaseModel):
        drive_path: str

    jobs = {}
    work = queue.Queue()
    lock = threading.Lock()

    def atomic_write(path, text):
        # Readers live on sibling containers; a torn read parses as corrupt
        # JSON and looks exactly like a missing job. Tmp + os.replace keeps
        # every observable state complete.
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("atomic write failed %s (%s)", path, exc)

    def checkpoint(key, stage, entry):
        try:
            d = checkpoint_root / key
            d.mkdir(parents=True, exist_ok=True)
            atomic_write(d / f"{stage}.json",
                         json.dumps({"stage": stage, "entry": entry}))
        except OSError as exc:
            log.warning("checkpoint write failed %s/%s: %s", key, stage, exc)

    def save_job(job):
        # Durable job envelopes: any container serves status for any job, so
        # concurrent panel polling across containers never sees a false 404.
        # Same Volume family as stage checkpoints (local-SSD fast); small
        # JSONs, pruned never (a job record is forensic history).
        try:
            d = checkpoint_root / "_jobs"
            d.mkdir(parents=True, exist_ok=True)
            atomic_write(d / f"{job['job_id']}.json", json.dumps({
                "job_id": job["job_id"], "footage_key": job["footage_key"],
                "drive_path": job["drive_path"], "state": job["state"],
                "shot_count": job.get("shot_count", 0),
                "duration_s": job.get("duration_s", 0.0),
                "stages": [job["stages"][n] for n in STAGES],
                "error": job["error"],
            }))
        except OSError as exc:
            log.warning("job envelope write failed %s (%s)", job["job_id"], exc)

    def load_job(jid):
        try:
            body = json.loads((checkpoint_root / "_jobs" / f"{jid}.json").read_text(
                encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(body, dict) or body.get("job_id") != jid:
            return None
        stages = {s["name"]: s for s in body.get("stages", []) if "name" in s}
        return {
            "job_id": body["job_id"], "footage_key": body.get("footage_key", ""),
            "drive_path": body.get("drive_path", ""), "state": body.get("state", "error"),
            "shot_count": body.get("shot_count", 0), "duration_s": body.get("duration_s", 0.0),
            "stages": {n: stages.get(n, {"name": n, "state": "pending", "done": 0, "total": 0})
                       for n in STAGES},
            "error": body.get("error"),
        }

    def progress(jid, stage, done, total):
        with lock:
            job = jobs.get(jid)
            if job is None:
                return
            job["stages"][stage] = {
                "name": stage, "state": "running", "done": int(done), "total": int(total),
            }
            key = job["footage_key"]
            save_job(job)
        checkpoint(key, stage, {"name": stage, "state": "running", "done": int(done), "total": int(total)})

    def worker():
        while True:
            jid = work.get()
            try:
                with lock:
                    job = jobs.get(jid)
                if job is None:
                    continue
                with lock:
                    job["state"] = "running"
                    save_job(job)
                out = artifacts_root / job["footage_key"]
                progress(jid, "upload", 0, 1)
                src = resolve_source(job["drive_path"])
                if not src.is_file():
                    raise FileNotFoundError(
                        f"footage not found: {job['drive_path']} (expected at {src})"
                    )
                progress(jid, "upload", int(src.stat().st_size), int(src.stat().st_size))
                summary = run_all(
                    src, out,
                    lambda st, d, t: progress(jid, st, d, t),
                )
                with lock:
                    for n in STAGES:
                        job["stages"][n]["state"] = "done"
                    job["state"] = "done"
                    job["shot_count"] = summary["shot_count"]
                    job["duration_s"] = summary["duration_s"]
                    save_job(job)
            except Exception as exc:  # noqa: BLE001 — job error, never a crash
                import traceback

                log.exception("job %s failed: %s", jid, exc)
                # Traceback tail (not just str(exc)): names the failing call
                # (e.g. which model load deserialized badly). Capped; paths
                # only, never secrets.
                tail = traceback.format_exc(limit=5)[-1200:]
                with lock:
                    job = jobs.get(jid)
                    if job is not None:
                        job["state"] = "error"
                        job["error"] = f"{exc}\n{tail}"[:2000]
                        save_job(job)
            finally:
                work.task_done()

    threading.Thread(target=worker, daemon=True, name="tempo-modal-jobs").start()

    def check(auth_header):
        want = auth_token or os.environ.get("BACKEND_TOKEN", "")
        if not want:
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "NO_TOKEN", "message": "backend token not configured"}},
            )
        if auth_header != f"Bearer {want}":
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHORIZED", "message": "bad token"}},
            )
        return None

    app = FastAPI(title="Tempo backend")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/health")
    def health():
        try:
            import torch

            gpu = torch.cuda.is_available()
        except ImportError:
            gpu = False
        return {"status": "ok", "gpu": gpu}

    @app.post("/index")
    def index(body: IndexReq, authorization: str | None = Header(default=None)):
        err = check(authorization)
        if err is not None:
            return err
        if not body.drive_path or not body.drive_path.strip():
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "BAD_PATH", "message": "drive_path required"}},
            )
        jid = "job_" + uuid.uuid4().hex[:8]
        key = Path(body.drive_path).parent.name or jid
        with lock:
            jobs[jid] = {
                "job_id": jid, "footage_key": key, "drive_path": body.drive_path,
                "state": "queued", "shot_count": 0,
                "duration_s": 0.0, "stages": _blank_stages(), "error": None,
            }
            save_job(jobs[jid])
        work.put(jid)
        return {"job_id": jid, "drive_path": body.drive_path, "footage_key": key}

    @app.get("/jobs/{jid}")
    def job_status(jid: str, authorization: str | None = Header(default=None)):
        err = check(authorization)
        if err is not None:
            return err
        with lock:
            job = jobs.get(jid)
        if job is None:
            # Cross-container read: the job may live on a sibling that has
            # since scaled to zero. Envelopes persist on the shared Volume.
            job = load_job(jid)
        if job is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "NOT_FOUND", "message": "unknown job"}},
            )
        return {
            "job_id": job["job_id"], "footage_key": job["footage_key"],
            "state": job["state"], "shot_count": job["shot_count"],
            "duration_s": job["duration_s"],
            "stages": [job["stages"][n] for n in STAGES], "error": job["error"],
        }

    @app.get("/search")
    def search(
        q: str = Query(min_length=1),
        top_k: int = Query(default=8, ge=1, le=50),
        footage_keys: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
    ):
        import time

        import numpy as _np

        t0 = time.perf_counter()
        err = check(authorization)
        if err is not None:
            return err
        # Corpus source of truth is artifact dirs on disk (survives restarts).
        if footage_keys:
            keys = footage_keys.split(",")
        else:
            keys = sorted(
                d.name for d in artifacts_root.iterdir()
                if d.is_dir() and (d / "shots.json").is_file()
            ) if artifacts_root.is_dir() else []
        mats_v, mats_d, mats_c, metas, bm25_all = [], [], [], [], []
        for key in keys:
            root = artifacts_root / key
            try:
                shots = json.loads((root / "shots.json").read_text(encoding="utf-8"))
                npz = _np.load(root / "embeddings.npz")
                order = sorted(range(len(shots)), key=lambda i: shots[i]["shot_id"])
                mats_v.append(npz["visual"][order])
                mats_d.append(npz["dialogue"][order])
                mats_c.append(npz["caption"][order])
                for i in order:
                    s = shots[i]
                    metas.append({
                        "footage_key": key, "shot_id": s["shot_id"],
                        "start_s": s["start_s"], "end_s": s["end_s"],
                        "transcript": s.get("transcript", ""),
                        "caption": s.get("caption", ""),
                        "entities": s.get("entities", []),
                        "text_context": (
                            s.get("transcript", "") + " " + s.get("caption", "")
                        ).strip(),
                    })
                with open(root / "bm25.pkl", "rb") as f:
                    index = pickle.load(f)
                bm25_all.append(
                    _np.asarray(index.get_scores(q.lower().split()), dtype=float)
                )
            except (OSError, ValueError, KeyError, pickle.PickleError) as exc:
                log.warning("skipping %s (%s)", key, exc)
        if not metas:
            return {"query": q, "took_ms": int((time.perf_counter() - t0) * 1000), "results": []}
        if embed_query is None:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MODEL_NOT_LOADED", "message": "text model not loaded"}},
            )
        qv = embed_query(q)
        V = _np.vstack(mats_v).astype(_np.float32)
        D = _np.vstack(mats_d).astype(_np.float32)
        C = _np.vstack(mats_c).astype(_np.float32)
        B = _np.concatenate(bm25_all).astype(float)
        shot_ents = [m["entities"] for m in metas]
        ctxs = [m["text_context"] for m in metas]
        # Query entities via the shared extractor when available (GPU); the
        # anchor/entity paths degrade to 0 honestly without it.
        try:
            from .ner import _extract_entities

            qe = _extract_entities(q)
        except Exception:  # noqa: BLE001 — NER optional, see app.py precedent
            qe = []
        out = scoring_module.score_query(
            qv, V, D, C, B, qe, shot_ents, ctxs, 0.45, 0.40, 0.15, 0.15
        )
        top = _np.argsort(-out["final"], kind="stable")[:top_k]
        results = []
        for idx in top:
            m = metas[int(idx)]
            wk = scoring_module.KEY_NAMES[int(out["winner"][idx])]
            results.append({
                "footage_key": m["footage_key"], "shot_id": m["shot_id"],
                "source_path": "",  # local service backfills from its registry
                "start_s": m["start_s"], "end_s": m["end_s"],
                "score": float(out["final"][idx]), "winning_key": wk,
                "raw_cos": {
                    "visual": float(out["key_stack"][0, idx]),
                    "dialogue": float(out["key_stack"][1, idx]),
                    "caption": float(out["key_stack"][2, idx]),
                },
                "contributions": {
                    "dense": float(out["dense_c"][idx]),
                    "bm25": float(out["bm25_c"][idx]),
                    "anchor": float(out["anchor_c"][idx]),
                    "entity_boost": float(out["boost"][idx]),
                },
                "transcript": m["transcript"], "caption": m["caption"],
                "entities": m["entities"],
            })
        return {"query": q, "took_ms": int((time.perf_counter() - t0) * 1000), "results": results}

    @app.get("/thumb/{key}/{sid}.jpg")
    def thumb(key: str, sid: int, authorization: str | None = Header(default=None)):
        err = check(authorization)
        if err is not None:
            return err
        for name in (f"keyframe_{sid}.jpg", f"shot_{sid}.jpg"):
            path = artifacts_root / key / "thumbs" / name
            if path.is_file():
                return FileResponse(
                    path, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "unknown thumbnail"}},
        )

    @app.get("/debug/disk")
    def debug_disk(authorization: str | None = Header(default=None)):
        # Trial diagnostics (auth-gated like everything else): disk pressure
        # and model-cache inventory. Distinguishes truncated downloads
        # (small/corrupt files) from version mismatches without container SSH.
        # Sizes only — never file contents, never secrets.
        import shutil

        err = check(authorization)
        if err is not None:
            return err
        try:
            usage = shutil.disk_usage(str(artifacts_root))
        except OSError:
            usage = None
        cache_roots = []
        for var in ("HF_HOME", "HF_HUB_CACHE", "EASYOCR_MODULE_PATH"):
            val = os.environ.get(var)
            if val:
                cache_roots.append(val)
        cache_roots.append(os.path.expanduser("~/.cache/huggingface"))
        inventory = []
        seen = set()
        for root in cache_roots:
            p = Path(root)
            if not p.is_dir() or str(p) in seen:
                continue
            seen.add(str(p))
            total, files = 0, []
            for f in sorted(p.rglob("*"))[:200]:
                if f.is_file():
                    try:
                        sz = f.stat().st_size
                    except OSError:
                        sz = -1
                    total += max(sz, 0)
                    files.append({"path": str(f.relative_to(p)), "bytes": sz})
            inventory.append({"root": str(p), "bytes": total, "files": files})
        return {
            "disk": (
                {"total": usage.total, "used": usage.used, "free": usage.free}
                if usage else None
            ),
            "caches": inventory,
        }

    return app
