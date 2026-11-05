"""Tests der Token-Erneuerung: Ohne sie antwortet die Agenten-API nach 10 Minuten 401.

Die Sitzung liegt serverseitig; hier wird sie durch ein einfaches Wörterbuch ersetzt.
Die Tests laufen ohne pytest-asyncio: jede Prüfung startet ihre Ereignisschleife selbst.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

import httpx
import pytest
from starlette.requests import Request

from officeassistant.settings import Settings
from officeassistant.ui import auth


class Stub:
    oidc_issuer = "http://127.0.0.1:8180/realms/oa"
    oidc_client_id = "oa-ui"
    oidc_client_secret = "secret"
    oidc_redirect_url = "http://127.0.0.1:8099/auth/callback"
    token_key = "x" * 44
    db_url = "postgresql://unbenutzt"
    ui_base_url = "http://127.0.0.1:8099"


SETTINGS: Any = cast(Settings, Stub())


class _Store:
    """Ersetzt den Datenbankspeicher; merkt sich die geschriebenen Token."""

    writes: list[dict[str, Any]] = []

    def __init__(self, tokens: dict[str, Any]) -> None:
        self.tokens = tokens

    def load(self, sid: str) -> dict[str, Any] | None:
        return {
            "subject": "sub-1",
            "email": "alice@example.org",
            "name": "Alice",
            "tokens": self.tokens,
        }

    def update_tokens(self, sid: str, tokens: dict[str, Any], expires_at: float) -> None:
        self.writes.append(dict(tokens))


def _session(expires_in: float, refresh_token: str = "refresh-1") -> dict[str, Any]:
    return {
        auth.SESSION_KEY: "sid-1",
        "tokens": {
            "access_token": "alt",
            "expires_at": time.time() + expires_in,
            "id_token": "id-1",
            "refresh_token": refresh_token,
        },
    }


def _token(monkeypatch, session: dict[str, Any]) -> str:
    store = _Store(session["tokens"])
    _Store.writes = []
    monkeypatch.setattr(auth, "session_store", lambda settings: store)
    request = Request({"type": "http", "session": {auth.SESSION_KEY: session[auth.SESSION_KEY]}})
    return asyncio.run(auth.access_token(request, SETTINGS))


def test_valid_token_is_used_without_a_request(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("Kein Netzzugriff erwartet")

    monkeypatch.setattr(auth.httpx, "post", boom)

    assert _token(monkeypatch, _session(300)) == "alt"


def test_expired_token_is_refreshed_and_stored(monkeypatch):
    monkeypatch.setattr(
        auth, "discover", lambda settings: {"token_endpoint": "http://kc/token"}
    )

    def fake_post(url, **kwargs):
        assert url == "http://kc/token"
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "refresh-1"
        return httpx.Response(
            200,
            json={"access_token": "neu", "refresh_token": "refresh-2", "expires_in": 600},
        )

    monkeypatch.setattr(auth.httpx, "post", fake_post)

    assert _token(monkeypatch, _session(-10)) == "neu"
    assert _Store.writes, "Erneuerte Token müssen gespeichert werden"
    gespeichert = _Store.writes[-1]
    assert gespeichert["access_token"] == "neu"
    assert gespeichert["refresh_token"] == "refresh-2"
    assert gespeichert["expires_at"] > time.time()


def test_failed_refresh_forces_a_new_login(monkeypatch):
    monkeypatch.setattr(
        auth, "discover", lambda settings: {"token_endpoint": "http://kc/token"}
    )
    monkeypatch.setattr(
        auth.httpx, "post", lambda url, **kwargs: httpx.Response(400, json={})
    )

    with pytest.raises(auth.NotAuthenticated):
        _token(monkeypatch, _session(-10))


def test_expired_without_refresh_token_forces_a_new_login(monkeypatch):
    with pytest.raises(auth.NotAuthenticated):
        _token(monkeypatch, _session(-10, refresh_token=""))
