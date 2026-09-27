"""Engine /v1 response models (docs/engine-api.md)."""

from typing import Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    gpu: bool
    device: str
    signature: str
    stages: list[str]
    query_models: Literal["loading", "ready", "error"]


class LibraryEntry(BaseModel):
    content_id: str
    state: Literal["missing", "partial", "uploaded", "indexing", "ready", "stale", "error"]
    needs_upload: bool
    received: int = 0
    size: int = 0
    job_id: str | None = None
    shot_count: int = 0
    duration_s: float = 0.0
    fps: float = 0.0
    error: str | None = None


class UploadState(BaseModel):
    content_id: str
    received: int
    size: int
    complete: bool


class IndexRequest(BaseModel):
    content_id: str


class IndexResponse(BaseModel):
    job_id: str | None
    state: Literal["queued", "running", "done"]


class Stage(BaseModel):
    name: str
    state: Literal["pending", "running", "done", "error"]
    done: int = 0
    total: int = 0


class Job(BaseModel):
    job_id: str
    content_id: str
    state: Literal["queued", "running", "done", "error"]
    stages: list[Stage]
    error: str | None = None
    shot_count: int = 0
    duration_s: float = 0.0
    fps: float = 0.0


class Contributions(BaseModel):
    visual: float
    dialogue: float
    caption: float
    bm25: float
    entity: float
    anchor: float


class RawCos(BaseModel):
    visual: float
    dialogue: float | None
    caption: float


class SearchResult(BaseModel):
    content_id: str
    shot_id: int
    scene_id: int
    start_s: float
    end_s: float
    score: float
    contributions: Contributions
    raw_cos: RawCos
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
