"""Der Grund für „Anmeldung erforderlich" direkt nach der Anmeldung.

Ein Cookie mit drei JWT war 4696 Bytes groß. Browser verwerfen Cookies über 4096 Bytes,
also war die Sitzung nach der Anmeldung sofort weg. Diese Tests halten den Fehler fest.
"""

from __future__ import annotations

import base64
import json
import os
import time

import pytest
from cryptography.fernet import Fernet
from starlette.requests import Request

from officeassistant.store import db
from officeassistant.store.ui_sessions import SESSION_KEY, SessionStore
from officeassistant.ui import auth

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


class _Settings:
    db_url = DB_URL
    token_key = Fernet.generate_key().decode()


def setup_module() -> None:
    if not DB_URL:
        return
    conn = db.connect(DB_URL)
    try:
        db.migrate(conn)
    finally:
        conn.close()


def _cookie_value(payload: dict) -> int:
    return len(base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()))


def test_session_cookie_stays_small_with_real_tokens(monkeypatch):
    store = SessionStore(DB_URL, _Settings.token_key)
    jwt = "a" * 1200
    sid = store.create(
        subject="sub-cookie",
        email="alice@example.org",
        name="Alice",
        tokens={
            "access_token": jwt,
            "refresh_token": "b" * 700,
            "id_token": "c" * 1300,
            "expires_at": time.time() + 600,
        },
        expires_at=time.time() + 3600,
    )
    try:
        # So sieht das Cookie jetzt aus: nur die Kennung.
        assert _cookie_value({SESSION_KEY: sid}) < 200

        # Und die Anwendung findet damit die Token wieder.
        monkeypatch.setattr(auth, "session_store", lambda settings: store)
        request = Request({"type": "http", "session": {SESSION_KEY: sid}})
        identity = auth.identity(request, _Settings())  # type: ignore[arg-type]

        assert identity is not None
        assert identity.email == "alice@example.org"
        assert identity.access_token == jwt
        assert identity.expired is False

        # Zum Vergleich: die alte Bauform sprengt die Grenze von 4096 Bytes.
        alt = {
            "oa_user": {
                "subject": "sub-cookie",
                "email": "alice@example.org",
                "name": "Alice",
                "access_token": jwt,
                "refresh_token": "b" * 700,
                "id_token": "c" * 1300,
                "expires_at": time.time() + 600,
            }
        }
        assert _cookie_value(alt) > 4096
    finally:
        store.delete(sid)
