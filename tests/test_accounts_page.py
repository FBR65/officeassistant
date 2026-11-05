"""Tests der Seite „Postfächer": Verbinden und Trennen.

Die Seiten selbst werden im Browser geprüft; hier geht es um die schreibenden Wege,
also um das, was Daten verändert.
"""

from __future__ import annotations

import os
import time

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from officeassistant.store import db
from officeassistant.store.tokens import TokenStore
from officeassistant.ui import accounts, auth

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


@pytest.fixture()
def client(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(accounts.SETTINGS, "db_url", DB_URL, raising=False)
    monkeypatch.setattr(accounts.SETTINGS, "token_key", key, raising=False)

    conn = db.connect(DB_URL)
    db.migrate(conn)
    conn.execute(
        "TRUNCATE audit, tool_policy, credential, mail_account, task, routine, "
        "memory_entry, app_user RESTART IDENTITY CASCADE"
    )
    conn.commit()
    conn.close()

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    accounts.register(app)

    @app.get("/_anmelden")
    def _anmelden(request: Request, sub: str = "alice-sub", mail: str = "alice@example.org"):
        # Die Sitzung liegt serverseitig; im Cookie steht nur die Kennung.
        sid = auth.session_store(accounts.SETTINGS).create(
            subject=sub,
            email=mail,
            name="Alice",
            tokens={"access_token": "token", "expires_at": time.time() + 300},
            expires_at=time.time() + 600,
        )
        request.session[auth.SESSION_KEY] = sid
        return {"ok": True}

    with TestClient(app, follow_redirects=False) as test_client:
        test_client.get("/_anmelden")
        yield test_client


def _accounts(user_id: str):
    conn = db.connect(DB_URL)
    try:
        return TokenStore(conn, accounts.SETTINGS.token_key).accounts(user_id)
    finally:
        conn.close()


def test_connect_creates_an_account(client):
    response = client.post(
        "/postfaecher/verbinden", data={"anbieter": "fake", "adresse": "alice@example.org"}
    )

    assert response.status_code == 303
    assert [a.address for a in _accounts("alice-sub")] == ["alice@example.org"]


def test_invalid_input_is_refused(client):
    response = client.post(
        "/postfaecher/verbinden", data={"anbieter": "fake", "adresse": "keine-adresse"}
    )

    assert response.status_code == 303
    assert "ung" in response.headers["location"]
    assert _accounts("alice-sub") == []


def test_disconnect_removes_the_own_account(client):
    client.post("/postfaecher/verbinden", data={"anbieter": "fake", "adresse": "a@example.org"})
    account = _accounts("alice-sub")[0]

    response = client.post(f"/postfaecher/{account.id}/trennen")

    assert response.status_code == 303
    assert _accounts("alice-sub") == []


def test_disconnect_of_a_foreign_account_is_refused(client):
    conn = db.connect(DB_URL)
    try:
        db.migrate(conn)
        conn.execute(
            "INSERT INTO app_user (id, email) VALUES ('bob-sub', 'bob@example.org') "
            "ON CONFLICT DO NOTHING"
        )
        conn.commit()
        foreign = TokenStore(conn, accounts.SETTINGS.token_key).save(
            "bob-sub", "fake", "bob@example.org", {}
        )
    finally:
        conn.close()

    response = client.post(f"/postfaecher/{foreign.id}/trennen")

    assert response.status_code == 303
    assert "geh" in response.headers["location"]
    assert len(_accounts("bob-sub")) == 1
