"""HTTP engine client (ADR-0008, docs/engine-api.md).

Single place for the engine base URL + bearer token, timeouts, and the
transport error mapping (stdlib urllib, no extra dependency). The URL and
token come from server config/env only — never user input, never logged.
Through Brev the URL is the supervised port-forward's local end.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

from .base import ASLEEP, TIMEOUT, UNREACHABLE, BackendProvider, Reply

log = logging.getLogger("tempo.backends.http")

ASLEEP_STATUS = (502, 503)


def configured(base_url: str) -> bool:
    return bool(base_url and base_url.startswith("http"))


class HttpBackend(BackendProvider):
    def __init__(self, base_url: str, token: str, timeout_s: float,
                 upload_timeout_s: float | None = None, bulk_timeout_s: float | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_s
        self._upload_timeout = upload_timeout_s or timeout_s
        self._bulk_timeout = bulk_timeout_s or timeout_s

    def _request(self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None,
                 data: bytes | None = None, timeout: float | None = None, binary: bool = False) -> Reply:
        if not configured(self._base):
            return Reply(False, 502, code=UNREACHABLE, message="engine URL not configured")
        url = self._base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            headers["Content-Type"] = "application/octet-stream"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout) as res:
                raw = res.read()
                return Reply(True, res.status, raw if binary else json.loads(raw.decode("utf-8") or "null"))
        except urllib.error.HTTPError as exc:
            return self._http_error(exc)
        except (socket.timeout, TimeoutError):
            return Reply(False, 504, code=TIMEOUT, message=f"{method} {path} timed out")
        except Exception as exc:  # refused, DNS, reset: the tunnel or engine is down
            if "timed out" in str(exc).lower():
                return Reply(False, 504, code=TIMEOUT, message=f"{method} {path} timed out")
            log.info("engine %s %s failed (%s)", method, path, exc)
            return Reply(False, 502, code=UNREACHABLE, message=str(exc)[:200])

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> Reply:
        try:
            err = json.loads(exc.read().decode("utf-8") or "{}").get("error") or {}
        except (ValueError, AttributeError):
            err = {}
        code, message = err.get("code"), err.get("message", "")
        if exc.code in ASLEEP_STATUS:
            return Reply(False, exc.code, code=ASLEEP, message=code or message)
        if exc.code == 401:
            return Reply(False, 401, code=UNREACHABLE, message="engine rejected the token")
        return Reply(False, exc.code, code=code or UNREACHABLE, message=message)

    def health(self) -> dict:
        reply = self._request("GET", "/v1/health")
        body = reply.body if reply.ok and isinstance(reply.body, dict) else {}
        return {"reachable": reply.ok, "gpu": bool(body.get("gpu", False)),
                "signature": str(body.get("signature", "")), "stages": list(body.get("stages", [])),
                "query_models": str(body.get("query_models", ""))}

    def library(self, content_id: str) -> Reply:
        return self._request("GET", f"/v1/library/{urllib.parse.quote(content_id)}")

    def upload_chunk(self, content_id: str, offset: int, size: int, name: str, data: bytes) -> Reply:
        return self._request("PUT", f"/v1/uploads/{urllib.parse.quote(content_id)}",
                             params={"offset": offset, "size": size, "name": name}, data=data,
                             timeout=self._upload_timeout)

    def submit_index(self, content_id: str) -> Reply:
        return self._request("POST", "/v1/index", json_body={"content_id": content_id})

    def job_status(self, job_id: str) -> Reply:
        return self._request("GET", f"/v1/jobs/{urllib.parse.quote(job_id)}")

    def search(self, q: str, top_k: int, content_ids: list[str] | None) -> Reply:
        params: dict = {"q": q, "top_k": top_k}
        if content_ids:
            params["content_ids"] = ",".join(content_ids)
        return self._request("GET", "/v1/search", params=params)

    def thumb_bytes(self, content_id: str, shot_id: int) -> Reply:
        return self._request("GET", f"/v1/library/{urllib.parse.quote(content_id)}/thumbs/{int(shot_id)}.jpg",
                             binary=True)

    def thumbs_tar(self, content_id: str) -> Reply:
        return self._request("GET", f"/v1/library/{urllib.parse.quote(content_id)}/thumbs.tar",
                             binary=True, timeout=self._bulk_timeout)
