"""Backend providers (ADR-0004, ADR-0008). The factory reads server config only."""

from ..config import Settings
from .base import ASLEEP, TIMEOUT, TRANSPORT_CODES, UNREACHABLE, BackendProvider, Reply
from .http_backend import HttpBackend, configured


def get_provider(s: Settings, timeout_s: float | None = None) -> BackendProvider | None:
    """The engine client, or None when no engine address is configured (neither
    TEMPO_BACKEND_URL nor a Brev instance) — callers surface BACKEND_UNREACHABLE."""
    url = s.engine_url
    if not configured(url):
        return None
    return HttpBackend(url, s.backend_token, timeout_s or s.backend_timeout_s,
                       upload_timeout_s=s.upload_timeout_s, bulk_timeout_s=s.backend_bulk_timeout_s)


__all__ = ["ASLEEP", "TIMEOUT", "TRANSPORT_CODES", "UNREACHABLE", "BackendProvider", "HttpBackend", "Reply",
           "configured", "get_provider"]
