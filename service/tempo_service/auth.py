"""Identity client + gate (ADR-0005).

Better Auth owns credentials (email+password, Google/GitHub); this module
owns everything the sidecar needs: exchanging logins, validating opaque
session tokens, caching by expiry, and persisting across restarts in the OS
keychain. Response shapes below are pinned to better-auth 1.7.5 as OBSERVED
live (auth/probe runs, see auth/README.md) — never guessed:

  POST /api/auth/sign-in/email {email,password}
    -> {redirect, token, user{id,name,email,...}} (+ session cookie)
  GET  /api/auth/get-session + Authorization: Bearer <token>
    -> {session{expiresAt,userId,...}, user{id,name,email,...}}
    -> null when absent/invalid (fail closed)

Trust boundary: the sidecar serves one local editor over 127.0.0.1. The
panel keeps the token in memory; the keychain copy survives restarts so
/boot restores UI state without re-login. Production per-request
enforcement lives at the gateway (P3); here the gate keeps anonymous
callers off GPU-burning routes.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("tempo.auth")

SERVICE = "tempo"
SKEW_S = 30.0


class AuthError(Exception):
    """Invalid credentials, unknown session, or unreachable auth service."""


def _parse_iso(ts: str) -> float:
    """'2026-09-29T14:43:35.000Z' (or without millis) -> epoch seconds."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _now() -> float:
    return time.time()


class AuthClient:
    """Thin HTTPS client for the Better Auth service. stdlib only."""

    def __init__(self, base_url: str, timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._cache: dict[str, tuple[dict, float]] = {}
        self._lock = threading.Lock()

    def _post(self, path: str, payload: dict) -> tuple[int, dict | None]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + path, data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as res:
                return res.status, json.loads(res.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8") or "{}")
            except (ValueError, OSError):
                return exc.code, None

    def _get_session_upstream(self, token: str) -> dict | None:
        req = urllib.request.Request(
            self._base_url + "/api/auth/get-session",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as res:
                return json.loads(res.read().decode("utf-8") or "null")
        except Exception as exc:  # network or HTTP error -> invalid here
            log.info("auth session check failed (%s)", exc)
            return None

    @staticmethod
    def _parse_user_envelope(body: dict) -> tuple[str, dict]:
        """{token, user{id,email,...}} -> (token, user). Fail closed."""
        try:
            token = body["token"]
            user = body["user"]
            user_id, email = user["id"], user.get("email", "")
        except (KeyError, TypeError, AttributeError) as exc:
            raise AuthError(f"unexpected auth response shape: {exc}")
        if not token or not user_id:
            raise AuthError("empty token or user id in auth response")
        return token, {"user_id": user_id, "email": email}

    @staticmethod
    def _parse_session_envelope(body: dict | None) -> dict | None:
        """{session{expiresAt,userId}, user{...}} -> cached identity or None."""
        try:
            if not body:
                return None
            session, user = body["session"], body["user"]
            return {
                "user_id": user["id"],
                "email": user.get("email", ""),
                "expires_at": _parse_iso(session["expiresAt"]),
            }
        except (KeyError, TypeError, AttributeError, ValueError):
            return None

    def sign_in(self, email: str, password: str) -> tuple[str, dict]:
        status, body = self._post(
            "/api/auth/sign-in/email", {"email": email, "password": password}
        )
        if status != 200 or not body:
            raise AuthError(f"sign-in rejected (status {status})")
        return self._parse_user_envelope(body)

    def sign_up(self, name: str, email: str, password: str) -> tuple[str, dict]:
        status, body = self._post(
            "/api/auth/sign-up/email",
            {"name": name, "email": email, "password": password},
        )
        if status != 200 or not body:
            raise AuthError(f"sign-up rejected (status {status})")
        return self._parse_user_envelope(body)

    def validate(self, token: str) -> dict | None:
        """Cached session validation. Returns identity or None (fail closed).
        Expired sessions — cached or fresh — validate to None and are evicted,
        so callers can trust a returned identity without rechecking expiry."""
        now = _now()
        with self._lock:
            hit = self._cache.get(token)
            if hit and hit[1] > now + SKEW_S:
                return hit[0]
        ident = self._parse_session_envelope(self._get_session_upstream(token))
        with self._lock:
            if ident is None or ident["expires_at"] <= now + SKEW_S:
                self._cache.pop(token, None)
                return None
            self._cache[token] = (ident, ident["expires_at"])
        return ident

    def drop(self, token: str) -> None:
        with self._lock:
            self._cache.pop(token, None)


class TokenStore:
    """Session persistence. OS keychain in production (Windows Credential
    Manager via keyring — verified roundtrip); memory backend for tests."""

    def __init__(self, backend: str = "keyring") -> None:
        self._backend = backend
        self._memory: dict[str, str] = {}

    def _keyring(self):  # type: ignore[no-untyped-def]
        try:
            import keyring
        except ImportError as exc:
            raise AuthError(f"keyring unavailable: {exc}")
        return keyring

    def save(self, token: str, user_id: str, email: str, expires_at: float) -> None:
        payload = json.dumps(
            {"token": token, "user_id": user_id, "email": email,
             "expires_at": expires_at}
        )
        if self._backend == "memory":
            self._memory["session"] = payload
            return
        self._keyring().set_password(SERVICE, "session", payload)

    def load(self) -> dict | None:
        try:
            raw = (
                self._memory.get("session")
                if self._backend == "memory"
                else self._keyring().get_password(SERVICE, "session")
            )
        except Exception as exc:  # locked vault, missing backend, etc.
            log.info("auth store unreadable (%s)", exc)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if not data.get("token") or not data.get("user_id"):
                return None
            return data
        except (ValueError, AttributeError):
            return None

    def clear(self) -> None:
        if self._backend == "memory":
            self._memory.pop("session", None)
            return
        try:
            self._keyring().delete_password(SERVICE, "session")
        except Exception as exc:  # already gone counts as cleared
            log.info("auth store clear (%s)", exc)


def current_user(token: str | None, client: AuthClient, store: TokenStore) -> dict | None:
    """Resolve identity: explicit Bearer token first, keychain session second.
    Returns {user_id, email} or None. Never raises."""
    if token:
        ident = client.validate(token)
        if ident:
            return {"user_id": ident["user_id"], "email": ident["email"]}
    saved = store.load()
    if not saved:
        return None
    try:
        if saved.get("expires_at", 0) < _now() + SKEW_S:
            return None
    except (TypeError, ValueError):
        return None
    ident = client.validate(saved["token"])
    if ident:
        return {"user_id": ident["user_id"], "email": ident["email"]}
    return None


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
