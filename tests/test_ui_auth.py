"""Tests der Anmeldeschicht ohne echten Aussteller.

Die Sitzung liegt serverseitig; hier wird der Sitzungsspeicher ersetzt.
"""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request

from officeassistant.ui import auth


def _request(sid: str | None) -> Request:
    scope: dict[str, Any] = {"type": "http"}
    if sid is not None:
        scope["session"] = {auth.SESSION_KEY: sid} if sid else {}
    return Request(scope)


class _Store:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.data = data

    def load(self, sid: str) -> dict[str, Any] | None:
        return self.data


def test_no_sid_means_no_identity(monkeypatch):
    monkeypatch.setattr(auth, "session_store", lambda settings: _Store(None))

    assert auth.identity(_request(None), object()) is None  # type: ignore[arg-type]
    assert auth.identity(_request(""), object()) is None  # type: ignore[arg-type]


def test_identity_is_read_from_the_server_side_session(monkeypatch):
    monkeypatch.setattr(
        auth,
        "session_store",
        lambda settings: _Store(
            {
                "subject": "abc-123",
                "email": "alice@example.org",
                "name": "Alice",
                "tokens": {"access_token": "token", "expires_at": time.time() + 300},
            }
        ),
    )

    identity = auth.identity(_request("sid-1"), object())  # type: ignore[arg-type]

    assert identity is not None
    assert identity.subject == "abc-123"
    assert identity.email == "alice@example.org"
    assert identity.expired is False


def test_expired_identity_is_flagged(monkeypatch):
    monkeypatch.setattr(
        auth,
        "session_store",
        lambda settings: _Store(
            {
                "subject": "abc-123",
                "email": "alice@example.org",
                "name": "Alice",
                "tokens": {"access_token": "token", "expires_at": time.time() - 10},
            }
        ),
    )

    identity = auth.identity(_request("sid-1"), object())  # type: ignore[arg-type]

    assert identity is not None
    assert identity.expired is True


def test_install_registers_the_three_routes(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setattr(
        auth,
        "discover",
        lambda settings: {
            "issuer": "http://127.0.0.1:8180/realms/oa",
            "authorization_endpoint": "http://127.0.0.1:8180/auth",
            "token_endpoint": "http://127.0.0.1:8180/token",
            "jwks_uri": "http://127.0.0.1:8180/certs",
        },
    )

    class Stub:
        oidc_issuer = "http://127.0.0.1:8180/realms/oa"
        oidc_client_id = "oa-ui"
        oidc_client_secret = "secret"
        oidc_redirect_url = "http://127.0.0.1:8099/auth/callback"
        token_key = "x" * 44
        db_url = "postgresql://unbenutzt"
        ui_base_url = "http://127.0.0.1:8099"

    app = FastAPI()
    auth.install(app, Stub())  # type: ignore[arg-type]

    paths = {route.path for route in app.routes}
    assert {"/login", "/auth/callback", "/logout"} <= paths
