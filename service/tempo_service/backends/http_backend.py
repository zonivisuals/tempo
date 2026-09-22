"""HTTPS backend client (ADR-0004).

Single place for backend base-URL + bearer-token handling, timeouts, and the
BACKEND_UNREACHABLE / BACKEND_ASLEEP / BACKEND_TIMEOUT error mapping (§3.4).
The URL and token come from server config/env only (TEMPO_BACKEND_URL,
TEMPO_BACKEND_TOKEN) — never user input, never git. The local service never
exposes beyond 127.0.0.1.

Error semantics:
  no URL configured        -> (ok=False, code=BACKEND_UNREACHABLE)
  connection refused/DNS   -> (ok=False, code=BACKEND_UNREACHABLE)
  gateway 502/503 (up, workers down) -> BACKEND_ASLEEP
  timeout                  -> BACKEND_TIMEOUT
"""

from __future__ import annotations

import logging

log = logging.getLogger("tempo.backends.http")


def configured(base_url: str) -> bool:
    return bool(base_url and base_url.startswith("http"))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def health(base_url: str, token: str, timeout_s: float) -> dict:
    """Probe shim GET /health. Never raises — returns reachable/gpu."""
    import urllib.error
    import urllib.request

    if not configured(base_url):
        return {"reachable": False, "gpu": False}
    try:
        req = urllib.request.Request(
            base_url.rstrip("/") + "/health", headers=_headers(token)
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            import json

            body = json.loads(res.read().decode("utf-8") or "{}")
        return {"reachable": True, "gpu": bool(body.get("gpu", False))}
    except Exception as exc:
        log.info("backend health probe failed (%s)", exc)
        return {"reachable": False, "gpu": False}


def index(
    base_url: str, token: str, storage_ref: str, timeout_s: float,
) -> tuple[bool, int, dict | None, str | None]:
    """POST /index → {job_id, footage_key}. Same error mapping."""
    import json
    import socket
    import urllib.error
    import urllib.request

    if not configured(base_url):
        return False, 502, None, "BACKEND_UNREACHABLE"
    url = base_url.rstrip("/") + "/index"
    # Wire field stays `drive_path` (docs/api.md contract); the value is an
    # opaque storage ref the backends resolve (Drive-shaped today, R2 tomorrow).
    data = json.dumps({"drive_path": storage_ref}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=data, headers={**_headers(token), "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.status, json.loads(res.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, exc.code, None, "BACKEND_ASLEEP"
        if exc.code == 401:
            return False, exc.code, None, "BACKEND_UNREACHABLE"
        return False, exc.code, None, "BACKEND_UNREACHABLE"
    except socket.timeout:
        return False, 504, None, "BACKEND_TIMEOUT"
    except TimeoutError:
        return False, 504, None, "BACKEND_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, 504, None, "BACKEND_TIMEOUT"
        log.info("backend index failed (%s)", exc)
        return False, 502, None, "BACKEND_UNREACHABLE"


def job_status(
    base_url: str, token: str, backend_job_id: str, timeout_s: float,
) -> tuple[bool, int, dict | None, str | None]:
    """GET /jobs/{id} → Colab job envelope. Same error mapping."""
    import json
    import socket
    import urllib.error
    import urllib.parse
    import urllib.request

    if not configured(base_url):
        return False, 502, None, "BACKEND_UNREACHABLE"
    url = base_url.rstrip("/") + "/jobs/" + urllib.parse.quote(backend_job_id)
    try:
        req = urllib.request.Request(url, headers=_headers(token))
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.status, json.loads(res.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, exc.code, None, "BACKEND_ASLEEP"
        return False, exc.code, None, "BACKEND_UNREACHABLE"
    except socket.timeout:
        return False, 504, None, "BACKEND_TIMEOUT"
    except TimeoutError:
        return False, 504, None, "BACKEND_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, 504, None, "BACKEND_TIMEOUT"
        log.info("backend job poll failed (%s)", exc)
        return False, 502, None, "BACKEND_UNREACHABLE"


def thumb_bytes(
    base_url: str, token: str, footage_key: str, shot_id: int, timeout_s: float,
) -> tuple[bool, bytes | None, str | None]:
    """GET /thumb/{key}/{id}.jpg → raw JPEG bytes (service fallback cache)."""
    import socket
    import urllib.error
    import urllib.parse
    import urllib.request

    if not configured(base_url):
        return False, None, "BACKEND_UNREACHABLE"
    url = (
        base_url.rstrip("/")
        + "/thumb/"
        + urllib.parse.quote(footage_key)
        + f"/{int(shot_id)}.jpg"
    )
    try:
        req = urllib.request.Request(url, headers=_headers(token))
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.read(), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, None, "BACKEND_ASLEEP"
        return False, None, "BACKEND_UNREACHABLE"
    except socket.timeout:
        return False, None, "BACKEND_TIMEOUT"
    except TimeoutError:
        return False, None, "BACKEND_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, None, "BACKEND_TIMEOUT"
        return False, None, "BACKEND_UNREACHABLE"


def search(
    base_url: str, token: str, q: str, top_k: int,
    footage_keys: str | None, timeout_s: float,
) -> tuple[bool, int, dict | None, str | None]:
    """Proxy GET /search to the shim.

    Returns (ok, status, body, error_code). error_code is one of
    BACKEND_UNREACHABLE / BACKEND_ASLEEP / BACKEND_TIMEOUT on failure.
    """
    import json
    import socket
    import urllib.error
    import urllib.parse
    import urllib.request

    if not configured(base_url):
        return False, 502, None, "BACKEND_UNREACHABLE"
    params = {"q": q, "top_k": str(top_k)}
    if footage_keys:
        params["footage_keys"] = footage_keys
    url = base_url.rstrip("/") + "/search?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=_headers(token))
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.status, json.loads(res.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, exc.code, None, "BACKEND_ASLEEP"
        return False, exc.code, None, "BACKEND_UNREACHABLE"
    except socket.timeout:
        return False, 504, None, "BACKEND_TIMEOUT"
    except TimeoutError:
        return False, 504, None, "BACKEND_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, 504, None, "BACKEND_TIMEOUT"
        log.info("backend search failed (%s)", exc)
        return False, 502, None, "BACKEND_UNREACHABLE"


class HttpBackend:
    """BackendProvider over plain HTTPS (urllib, stdlib only).

    Used for any backend speaking the docs/api.md contract — the Modal web
    endpoint today, other providers tomorrow. Timeouts bound once from
    config; token never logged.
    """

    def __init__(self, base_url: str, token: str, timeout_s: float) -> None:
        self._base_url = base_url
        self._token = token
        self._timeout_s = timeout_s

    def health(self) -> dict:
        return health(self._base_url, self._token, self._timeout_s)

    def submit_index(self, storage_ref: str) -> tuple:
        return index(self._base_url, self._token, storage_ref, self._timeout_s)

    def job_status(self, backend_job_id: str) -> tuple:
        return job_status(self._base_url, self._token, backend_job_id, self._timeout_s)

    def search(self, q: str, top_k: int, footage_keys: str | None) -> tuple:
        return search(self._base_url, self._token, q, top_k, footage_keys, self._timeout_s)

    def thumb_bytes(self, footage_key: str, shot_id: int) -> tuple:
        return thumb_bytes(self._base_url, self._token, footage_key, shot_id, self._timeout_s)
