"""Backend provider seam (ADR-0004, ADR-0008).

One interface for the indexing/search engine. The sidecar never touches a
transport (tunnel, SDK) outside this package. Calls never raise on transport
failure: they return a `Reply` whose `code` is the failure vocabulary the
sidecar and panel share —

  BACKEND_UNREACHABLE — no route to the engine (not configured, tunnel down,
                         refused, auth rejected)
  BACKEND_ASLEEP      — route alive, engine not serving (restarting, models
                         warming: 502/503)
  BACKEND_TIMEOUT     — request exceeded its budget (never hangs)

— or the engine's own error code for application errors (e.g. 409
OFFSET_MISMATCH, 409 SOURCE_MISSING), with the engine message kept.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

UNREACHABLE = "BACKEND_UNREACHABLE"
ASLEEP = "BACKEND_ASLEEP"
TIMEOUT = "BACKEND_TIMEOUT"
TRANSPORT_CODES = (UNREACHABLE, ASLEEP, TIMEOUT)


@dataclass
class Reply:
    ok: bool
    status: int
    body: Any = None  # parsed JSON, or bytes for binary routes
    code: str | None = None
    message: str = ""

    @property
    def transport_code(self) -> str:
        """The code to show the panel: transport codes as-is, anything else unreachable."""
        return self.code if self.code in TRANSPORT_CODES else UNREACHABLE


class BackendProvider(abc.ABC):
    """Engine client. Blocking calls with explicit timeouts (docs/engine-api.md)."""

    @abc.abstractmethod
    def health(self) -> dict:
        """→ {"reachable", "gpu", "signature", "stages", "query_models"}. Never raises."""

    @abc.abstractmethod
    def library(self, content_id: str) -> Reply:
        """GET /v1/library/{cid} → state, needs_upload, received/size, job_id, stats."""

    @abc.abstractmethod
    def upload_chunk(self, content_id: str, offset: int, size: int, name: str, data: bytes) -> Reply:
        """PUT /v1/uploads/{cid} — one chunk at `offset` (409 OFFSET_MISMATCH carries the engine offset)."""

    @abc.abstractmethod
    def submit_index(self, content_id: str) -> Reply:
        """POST /v1/index → {job_id | None, state}. Idempotent per content."""

    @abc.abstractmethod
    def job_status(self, job_id: str) -> Reply:
        """GET /v1/jobs/{id} → engine job envelope (stages in pipeline order)."""

    @abc.abstractmethod
    def search(self, q: str, top_k: int, content_ids: list[str] | None) -> Reply:
        """GET /v1/search → engine SearchResponse dict."""

    @abc.abstractmethod
    def thumb_bytes(self, content_id: str, shot_id: int) -> Reply:
        """GET one display thumb → JPEG bytes."""

    @abc.abstractmethod
    def thumbs_tar(self, content_id: str) -> Reply:
        """GET every display thumb as one tar → bytes."""
