"""Pydantic schemas for every endpoint (AGENTS.md §3.4, contracts in docs/api.md)."""

from typing import Literal

from pydantic import BaseModel, Field

from .vocabulary import (
    FOOTAGE_INDEXING,
    JOB_QUEUED,
    STAGE_PENDING,
    FootageState,
    JobState,
    StageState,
)


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
    # Held keys: unreadable stats, or size/mtime drift not yet confirmed over
    # consecutive syncs. Never enqueued; panel needs no changes (unknown field
    # ignored, counts stay consistent across the other four lists).
    pending: list[str] = Field(default_factory=list)
    jobs: list[str] = Field(default_factory=list)
    uploads: list[str] = Field(default_factory=list)


class StageStatus(BaseModel):
    name: str
    state: StageState = STAGE_PENDING
    done: int = 0
    total: int = 0


class JobStatus(BaseModel):
    job_id: str
    footage_key: str
    state: JobState = JOB_QUEUED
    reused: bool = False
    stages: list[StageStatus] = Field(default_factory=list)
    error: str | None = None
    # The kind of failure, closed vocabulary (docs/api.md). The panel renders this
    # and nothing else; `error` stays for the log and the registry entry.
    reason: str | None = None


class FootageInfo(BaseModel):
    footage_key: str
    path: str
    content_id: str = ""
    shot_count: int = 0
    duration_s: float = 0.0
    indexed_at: str | None = None
    state: FootageState = FOOTAGE_INDEXING
    reused: bool = False


class RawCos(BaseModel):
    visual: float = 0.0
    dialogue: float | None = None  # None: the shot has no dialogue vector
    caption: float = 0.0


class Contributions(BaseModel):
    """Weighted v4 fusion components (ADR-0009); they sum to `score`."""

    visual: float = 0.0
    dialogue: float = 0.0
    caption: float = 0.0
    bm25: float = 0.0
    entity: float = 0.0
    anchor: float = 0.0


class SearchResult(BaseModel):
    footage_key: str
    content_id: str
    shot_id: int
    scene_id: int = 0
    source_path: str
    start_s: float
    end_s: float
    score: float
    contributions: Contributions = Field(default_factory=Contributions)
    raw_cos: RawCos = Field(default_factory=RawCos)
    transcript: str = ""
    dialogue: str = ""
    caption: str = ""
    ocr: str = ""
    entities: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    took_ms: int
    entities: list[str] = Field(default_factory=list)
    results: list[SearchResult] = Field(default_factory=list)


class BackendStatus(BaseModel):
    reachable: bool = False
    gpu: bool = False
    tunnel: Literal["off", "starting", "up", "down"] = "off"
    signature: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    artifact_root: str
    backend: BackendStatus = Field(default_factory=BackendStatus)


class JobRetryResponse(BaseModel):
    job_id: str
    footage_key: str
