"""Backend providers (ADR-0004). Factory reads server config only."""

from .base import BackendError, BackendProvider
from .http_backend import HttpBackend, configured


def get_provider(backend: str, base_url: str, token: str, timeout_s: float):
    """Return the configured provider, or None for the local indexer path.

    `backend="local"` → None (caller runs the in-process pipeline).
    `backend="http"`  → HttpBackend bound to base_url/token (never user input).
    """
    if backend == "local":
        return None
    if backend == "http":
        if not configured(base_url):
            return None  # URL unset: caller falls back to local, logs it
        return HttpBackend(base_url, token, timeout_s)
    raise ValueError(f"unknown backend: {backend!r} (want local|http)")


__all__ = ["BackendError", "BackendProvider", "HttpBackend", "configured", "get_provider"]
