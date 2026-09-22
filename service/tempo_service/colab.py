"""Colab tunnel client (ADR-0002, P9-minimal).

Single place for ngrok URL + bearer token handling, timeouts, and the
COLAB_UNREACHABLE / COLAB_ASLEEP / COLAB_TIMEOUT error mapping (§3.4).
Token lives in config/env only, never in git. Panel passes per-session URL
via TEMPO_COLAB_URL; local service never exposes beyond 127.0.0.1.

Error semantics:
  no URL configured      -> (ok=False, code=COLAB_UNREACHABLE)
  connection refused/DNS -> (ok=False, code=COLAB_UNREACHABLE)
  tunnel 502/503 (ngrok up, notebook down) -> COLAB_ASLEEP
  timeout                -> COLAB_TIMEOUT
"""

from __future__ import annotations

import logging

log = logging.getLogger("tempo.colab")


def configured(colab_url: str) -> bool:
    return bool(colab_url and colab_url.startswith("http"))


def _headers(colab_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {colab_token}"} if colab_token else {}


def health(colab_url: str, colab_token: str, timeout_s: float) -> dict:
    """Probe shim GET /health. Never raises — returns reachable/gpu."""
    import urllib.error
    import urllib.request

    if not configured(colab_url):
        return {"reachable": False, "gpu": False}
    try:
        req = urllib.request.Request(
            colab_url.rstrip("/") + "/health", headers=_headers(colab_token)
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            import json

            body = json.loads(res.read().decode("utf-8") or "{}")
        return {"reachable": True, "gpu": bool(body.get("gpu", False))}
    except Exception as exc:
        log.info("colab health probe failed (%s)", exc)
        return {"reachable": False, "gpu": False}


def index(
    colab_url: str, colab_token: str, drive_path: str, timeout_s: float,
) -> tuple[bool, int, dict | None, str | None]:
    """POST /index {drive_path} → {job_id, footage_key}. Same error mapping."""
    import json
    import socket
    import urllib.error
    import urllib.request

    if not configured(colab_url):
        return False, 502, None, "COLAB_UNREACHABLE"
    url = colab_url.rstrip("/") + "/index"
    data = json.dumps({"drive_path": drive_path}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=data, headers={**_headers(colab_token), "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.status, json.loads(res.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, exc.code, None, "COLAB_ASLEEP"
        if exc.code == 401:
            return False, exc.code, None, "COLAB_UNREACHABLE"
        return False, exc.code, None, "COLAB_UNREACHABLE"
    except socket.timeout:
        return False, 504, None, "COLAB_TIMEOUT"
    except TimeoutError:
        return False, 504, None, "COLAB_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, 504, None, "COLAB_TIMEOUT"
        log.info("colab index failed (%s)", exc)
        return False, 502, None, "COLAB_UNREACHABLE"


def job_status(
    colab_url: str, colab_token: str, colab_job_id: str, timeout_s: float,
) -> tuple[bool, int, dict | None, str | None]:
    """GET /jobs/{id} → Colab job envelope. Same error mapping."""
    import json
    import socket
    import urllib.error
    import urllib.parse
    import urllib.request

    if not configured(colab_url):
        return False, 502, None, "COLAB_UNREACHABLE"
    url = colab_url.rstrip("/") + "/jobs/" + urllib.parse.quote(colab_job_id)
    try:
        req = urllib.request.Request(url, headers=_headers(colab_token))
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.status, json.loads(res.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, exc.code, None, "COLAB_ASLEEP"
        return False, exc.code, None, "COLAB_UNREACHABLE"
    except socket.timeout:
        return False, 504, None, "COLAB_TIMEOUT"
    except TimeoutError:
        return False, 504, None, "COLAB_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, 504, None, "COLAB_TIMEOUT"
        log.info("colab job poll failed (%s)", exc)
        return False, 502, None, "COLAB_UNREACHABLE"


def thumb_bytes(
    colab_url: str, colab_token: str, footage_key: str, shot_id: int, timeout_s: float,
) -> tuple[bool, bytes | None, str | None]:
    """GET /thumb/{key}/{id}.jpg → raw JPEG bytes (service fallback cache)."""
    import socket
    import urllib.error
    import urllib.parse
    import urllib.request

    if not configured(colab_url):
        return False, None, "COLAB_UNREACHABLE"
    url = (
        colab_url.rstrip("/")
        + "/thumb/"
        + urllib.parse.quote(footage_key)
        + f"/{int(shot_id)}.jpg"
    )
    try:
        req = urllib.request.Request(url, headers=_headers(colab_token))
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.read(), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, None, "COLAB_ASLEEP"
        return False, None, "COLAB_UNREACHABLE"
    except socket.timeout:
        return False, None, "COLAB_TIMEOUT"
    except TimeoutError:
        return False, None, "COLAB_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, None, "COLAB_TIMEOUT"
        return False, None, "COLAB_UNREACHABLE"


def search(
    colab_url: str, colab_token: str, q: str, top_k: int,
    footage_keys: str | None, timeout_s: float,
) -> tuple[bool, int, dict | None, str | None]:
    """Proxy GET /search to the shim.

    Returns (ok, status, body, error_code). error_code is one of
    COLAB_UNREACHABLE / COLAB_ASLEEP / COLAB_TIMEOUT on failure.
    """
    import json
    import socket
    import urllib.error
    import urllib.parse
    import urllib.request

    if not configured(colab_url):
        return False, 502, None, "COLAB_UNREACHABLE"
    params = {"q": q, "top_k": str(top_k)}
    if footage_keys:
        params["footage_keys"] = footage_keys
    url = colab_url.rstrip("/") + "/search?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=_headers(colab_token))
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return True, res.status, json.loads(res.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503):
            return False, exc.code, None, "COLAB_ASLEEP"
        return False, exc.code, None, "COLAB_UNREACHABLE"
    except socket.timeout:
        return False, 504, None, "COLAB_TIMEOUT"
    except TimeoutError:
        return False, 504, None, "COLAB_TIMEOUT"
    except Exception as exc:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return False, 504, None, "COLAB_TIMEOUT"
        log.info("colab search failed (%s)", exc)
        return False, 502, None, "COLAB_UNREACHABLE"
