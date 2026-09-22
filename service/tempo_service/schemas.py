"""Pydantic schemas for every endpoint (AGENTS.md §3.4, contracts in docs/api.md)."""

from typing import Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class FootageItem(BaseModel):
    path: str
    size: int
    mtime_ns: int
    item_id: int
    frame_rate: float = 25.0


class SyncRequest(BaseModel):
    footages: list[FootageItem] = Field(default_factory=list)


class SyncResponse(BaseModel):
    added: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    jobs: list[str] = Field(default_factory=list)
    uploads: list[str] = Field(default_factory=list)


class StageStatus(BaseModel):
    name: str
    state: Literal["pending", "running", "done", "error"] = "pending"
    done: int = 0
    total: int = 0


class JobStatus(BaseModel):
    job_id: str
    footage_key: str
    state: Literal["uploading", "queued-for-backend", "queued", "running", "done", "error"] = (
        "queued"
    )
    stages: list[StageStatus] = Field(default_factory=list)
    error: str | None = None


class FootageInfo(BaseModel):
    footage_key: str
    path: str
    drive_path: str = ""
    shot_count: int = 0
    duration_s: float = 0.0
    indexed_at: str | None = None
    state: Literal["uploading", "indexing", "ready", "stale", "error"] = "indexing"


class RawCos(BaseModel):
    visual: float = 0.0
    dialogue: float = 0.0
    caption: float = 0.0


class Contributions(BaseModel):
    dense: float = 0.0
    bm25: float = 0.0
    anchor: float = 0.0
    entity_boost: float = 0.0


class SearchResult(BaseModel):
    footage_key: str
    shot_id: int
    source_path: str
    start_s: float
    end_s: float
    score: float
    winning_key: str
    raw_cos: RawCos = Field(default_factory=RawCos)
    contributions: Contributions = Field(default_factory=Contributions)
    transcript: str = ""
    caption: str = ""
    entities: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    took_ms: int
    results: list[SearchResult] = Field(default_factory=list)


class BackendStatus(BaseModel):
    reachable: bool = False
    gpu: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    models_loaded: dict[str, bool] = Field(default_factory=dict)
    artifact_root: str
    backend: BackendStatus = Field(default_factory=BackendStatus)


class DriveAuthRequest(BaseModel):
    code: str = ""


class JobRetryResponse(BaseModel):
    job_id: str
    footage_key: str


class AuthSignupRequest(BaseModel):
    name: str = ""
    email: str = ""
    password: str = ""


class AuthLoginRequest(BaseModel):
    email: str = ""
    password: str = ""


class AuthSessionResponse(BaseModel):
    user_id: str
    email: str = ""


class AuthMeResponse(BaseModel):
    logged_in: bool = False
    user_id: str = ""
    email: str = ""
