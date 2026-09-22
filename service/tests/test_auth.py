"""Identity gate verification (ADR-0005).

Wire fixtures are the better-auth 1.7.5 shapes OBSERVED live against the
real package (auth/probe runs, auth/README.md) — never guessed:

  sign-in  -> {redirect, token, user{id,name,email,...}} + session cookie
  get-session (Bearer) -> {session{expiresAt,userId,...}, user{...}} | null

- AuthClient parses success/failure fail-closed; validate() caches by
  expiresAt and revalidates past it.
- TokenStore memory roundtrip; corrupt payload -> None.
- current_user(): header token first, keychain second, expiry honored.
- App: auth_mode=off leaves routes open (dev default, keeps the whole suite
  green); auth_mode=on gates /sync /search /jobs /retry with 401
  AUTH_REQUIRED, and /auth/* login/logout/me flows work end to end.
"""

import time

from fastapi.testclient import TestClient

from tempo_service import auth as auth_module
from tempo_service import registry


def _signin_body():
    return {
        "redirect": False,
        "token": "M61sWa2knTnYmg5LkJ3lFc5wPYQF6lax",
        "user": {"id": "user-1", "name": "T", "email": "t@tempo.test",
                 "emailVerified": False},
    }


def _session_body(expires_in=3600.0):
    exp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + expires_in))
    return {
        "session": {"expiresAt": exp, "token": "tok", "userId": "user-1",
                    "id": "sess-1"},
        "user": {"id": "user-1", "name": "T", "email": "t@tempo.test"},
    }


def test_parse_user_envelope_fail_closed():
    token, user = auth_module.AuthClient._parse_user_envelope(_signin_body())
    assert (token, user["user_id"], user["email"]) == (
        "M61sWa2knTnYmg5LkJ3lFc5wPYQF6lax", "user-1", "t@tempo.test")
    for bad in ({}, {"token": "", "user": {"id": "x"}}, {"token": "t"}, None):
        try:
            auth_module.AuthClient._parse_user_envelope(bad)
            raise AssertionError(f"should reject {bad!r}")
        except auth_module.AuthError:
            pass


def test_parse_session_envelope_fail_closed():
    ident = auth_module.AuthClient._parse_session_envelope(_session_body(600))
    assert ident["user_id"] == "user-1" and ident["expires_at"] > time.time()
    for bad in (None, {}, {"session": {}, "user": {}}, {"session": {"expiresAt": "nope"}, "user": {"id": "x"}}):
        assert auth_module.AuthClient._parse_session_envelope(bad) is None


def test_validate_caches_and_revalidates(monkeypatch):
    client = auth_module.AuthClient("http://127.0.0.1:9", 1.0)
    calls = {"n": 0}

    def fake_upstream(token):
        calls["n"] += 1
        return _session_body(600)

    monkeypatch.setattr(client, "_get_session_upstream", fake_upstream)
    assert client.validate("tok")["user_id"] == "user-1"
    assert client.validate("tok")["user_id"] == "user-1"
    assert calls["n"] == 1  # second hit served from cache

    def fake_expired(token):
        calls["n"] += 1
        return _session_body(-10)

    monkeypatch.setattr(client, "_get_session_upstream", fake_expired)
    client.drop("tok")
    assert client.validate("tok") is None


def test_token_store_memory_roundtrip_and_corrupt():
    store = auth_module.TokenStore(backend="memory")
    assert store.load() is None
    store.save("tok", "user-1", "t@tempo.test", time.time() + 60)
    assert store.load()["user_id"] == "user-1"
    store._memory["session"] = "not-json{{{"
    assert store.load() is None
    store.clear()
    assert store.load() is None


def test_current_user_header_first_then_keychain(monkeypatch):
    client = auth_module.AuthClient("http://127.0.0.1:9", 1.0)
    store = auth_module.TokenStore(backend="memory")
    # upstream honors only the saved token; anything else is invalid
    monkeypatch.setattr(
        client, "_get_session_upstream",
        lambda t: _session_body(600) if t == "saved-tok" else None,
    )
    store.save("saved-tok", "user-1", "t@tempo.test", time.time() + 600)
    assert auth_module.current_user(None, client, store)["user_id"] == "user-1"
    store.save("old", "user-9", "s@tempo.test", time.time() - 60)
    assert auth_module.current_user(None, client, store) is None
    assert auth_module.current_user("bogus", client, store) is None


def _authed_client(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    monkeypatch.setattr(app_module.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(registry.settings, "artifact_root", tmp_path)
    monkeypatch.setattr(app_module.settings, "backend", "local")
    monkeypatch.setattr(app_module.settings, "auth_mode", "on")
    monkeypatch.setattr(app_module.settings, "auth_url", "http://127.0.0.1:9")
    monkeypatch.setattr(app_module.settings, "token_store", "memory")
    return TestClient(app_module.create_app())


def test_protected_routes_need_session(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    assert client.post("/sync", json={"footages": []}).status_code == 401
    assert client.post("/sync", json={"footages": []}).json()["error"]["code"] == "AUTH_REQUIRED"
    assert client.get("/search", params={"q": "x"}).status_code == 401
    assert client.get("/jobs/none").status_code == 401
    assert client.post("/jobs/none/retry").status_code == 401
    assert client.post("/footage/none/retry").status_code == 401
    # public surface stays public (loader must work pre-login; thumbs are
    # <img> tags that cannot send headers)
    assert client.get("/health").status_code == 200
    assert client.get("/footage").status_code == 200
    assert client.get("/host/host.jsx").status_code == 200
    me = client.get("/auth/me").json()
    assert me == {"logged_in": False, "user_id": "", "email": ""}


def test_login_logout_me_flow(tmp_path, monkeypatch):
    import tempo_service.app as app_module

    client = _authed_client(tmp_path, monkeypatch)

    def fake_sign_in(self, email, password):
        if (email, password) != ("t@tempo.test", "s3cret-pass"):
            raise auth_module.AuthError("bad credentials")
        return "tok-1", {"user_id": "user-1", "email": email}

    def fake_validate(self, token):
        assert token == "tok-1"
        return {"user_id": "user-1", "email": "t@tempo.test",
                "expires_at": time.time() + 600}

    monkeypatch.setattr(auth_module.AuthClient, "sign_in", fake_sign_in)
    monkeypatch.setattr(auth_module.AuthClient, "validate", fake_validate)

    r = client.post("/auth/login", json={"email": "t@tempo.test", "password": "s3cret-pass"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "user-1", "email": "t@tempo.test"}
    # stored session now authenticates headerless requests (single-user box)
    assert client.post("/sync", json={"footages": []}).status_code == 200
    assert client.get("/auth/me").json()["logged_in"] is True
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.get("/auth/me").json()["logged_in"] is False
    assert client.post("/sync", json={"footages": []}).status_code == 401

    r = client.post("/auth/login", json={"email": "t@tempo.test", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REJECTED"
