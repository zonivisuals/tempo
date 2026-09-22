"""Backend provider seam (ADR-0004).

One interface for every indexing/search backend. The local service never
touches backend-specific transports (ngrok tunnels, SDKs) outside this
package. Method return shapes mirror docs/api.md; error codes are the only
failure vocabulary the service and panel share:

  BACKEND_UNREACHABLE — no route to the backend (not configured, DNS/refused,
                         auth rejected)
  BACKEND_ASLEEP      — route alive, workers down (scale-to-zero, preemption)
  BACKEND_TIMEOUT     — request exceeded its budget (never hangs)
"""

from __future__ import annotations

import abc


class BackendError(Exception):
    """Raised by providers that prefer exceptions over (ok, code) tuples."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class BackendProvider(abc.ABC):
    """Indexing/search backend. All methods are blocking with explicit
    timeouts; none raise on transport failure — they return ok=False plus a
    BACKEND_* code (or raise BackendError with .code set)."""

    @abc.abstractmethod
    def health(self) -> dict:
        """→ {"reachable": bool, "gpu": bool}. Never raises."""

    @abc.abstractmethod
    def submit_index(self, storage_ref: str) -> tuple[bool, int, dict | None, str | None]:
        """Enqueue indexing of storage_ref (e.g. tempo/<key>/<basename>).
        → (ok, http_status, {"job_id", "footage_key", ...} | None, code | None)."""

    @abc.abstractmethod
    def job_status(self, backend_job_id: str) -> tuple[bool, int, dict | None, str | None]:
        """Poll one backend job. → (ok, http_status, job_envelope | None, code | None).
        The envelope carries {job_id, footage_key, state, stages, error,
        shot_count, duration_s} with stages in STAGES order (§3.2)."""

    @abc.abstractmethod
    def search(
        self, q: str, top_k: int, footage_keys: str | None
    ) -> tuple[bool, int, dict | None, str | None]:
        """Run §3.5 fusion remotely. → (ok, http_status, SearchResponse-dict | None, code | None)."""

    @abc.abstractmethod
    def thumb_bytes(self, footage_key: str, shot_id: int) -> tuple[bool, bytes | None, str | None]:
        """Fetch one keyframe JPEG. → (ok, bytes | None, code | None)."""
