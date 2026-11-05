"""Verwaltungsseite: Zutritt, Anlegen, Rolle, Sperren (SPEC 2026-11-05, N2 bis N4)."""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from officeassistant.store import db
from officeassistant.store.users import UserStore
from officeassistant.ui import admin_page, auth

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


def _app_fuer(subject: str):
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    admin_page.register(app)

    @app.get("/_anmelden")
    def _anmelden(request: Request):
        sid = auth.session_store(admin_page.SETTINGS).create(
            subject=subject,
            email=f"{subject}@example.org",
            name=subject,
            tokens={"access_token": "t", "expires_at": time.time() + 300},
            expires_at=time.time() + 600,
        )
        request.session[auth.SESSION_KEY] = sid
        return {"ok": True}

    return app


@pytest.fixture()
def umgebung(monkeypatch):
    monkeypatch.setattr(admin_page.SETTINGS, "db_url", DB_URL, raising=False)
    monkeypatch.setattr(admin_page, "db", db, raising=False)
    conn = db.connect(DB_URL)
    db.migrate(conn)
    conn.execute("TRUNCATE app_user, audit RESTART IDENTITY CASCADE")
    conn.execute(
        "INSERT INTO app_user (id, email, display_name, role) VALUES (%s, %s, %s, %s)",
        ("u-admin", "chef@example.org", "Chefin", "admin"),
    )
    conn.execute(
        "INSERT INTO app_user (id, email, display_name, role) VALUES (%s, %s, %s, %s)",
        ("u-member", "mit@example.org", "Mitglied", "member"),
    )
    conn.commit()
    conn.close()
    yield


def _client(subject: str) -> TestClient:
    client = TestClient(_app_fuer(subject), follow_redirects=False)
    client.get("/_anmelden")
    return client


def _nutzer(user_id: str) -> Any:
    conn = db.connect(DB_URL, autocommit=True)
    try:
        return UserStore(conn).get(user_id)
    finally:
        conn.close()


def _protokoll() -> list[tuple[str, str]]:
    conn = db.connect(DB_URL, autocommit=True)
    try:
        rows = conn.execute(
            "SELECT user_id, tool FROM audit ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [(str(row["user_id"]), str(row["tool"])) for row in rows]


def test_only_admins_may_use_the_page(umgebung):
    conn = db.connect(DB_URL, autocommit=True)
    try:
        assert admin_page._darf_verwalten(conn, "u-admin") is True
        assert admin_page._darf_verwalten(conn, "u-member") is False
        assert admin_page._darf_verwalten(conn, "unbekannt") is False
    finally:
        conn.close()


def test_the_page_lists_every_user(umgebung):
    conn = db.connect(DB_URL, autocommit=True)
    try:
        html = admin_page._tabelle(UserStore(conn).all_users())
    finally:
        conn.close()

    assert "chef@example.org" in html
    assert "mit@example.org" in html
    assert "Verwaltung" in html


def test_the_admin_creates_a_user_and_writes_the_audit_log(umgebung, monkeypatch):
    angelegt: dict[str, Any] = {}

    class _FakeKeycloak:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def create_user(self, nutzer) -> str:
            angelegt["nutzer"] = nutzer
            return "kc-neu-1"

    monkeypatch.setattr(admin_page, "KeycloakAdmin", _FakeKeycloak)

    antwort = _client("u-admin").post(
        "/verwaltung/anlegen",
        data={
            "anzeigename": "Neue Person",
            "email": "neu@example.org",
            "benutzername": "neu",
            "passwort": "geheim123",
            "rolle": "member",
        },
    )

    assert antwort.status_code == 303
    assert angelegt["nutzer"].benutzername == "neu"
    neu = _nutzer("kc-neu-1")
    assert neu is not None and neu.email == "neu@example.org"
    assert ("u-admin", "verwaltung.nutzer_angelegt") in _protokoll()


def test_a_member_cannot_create_users(umgebung, monkeypatch):
    monkeypatch.setattr(
        admin_page, "KeycloakAdmin", lambda *a, **k: pytest.fail("Keycloak nicht aufrufen")
    )

    antwort = _client("u-member").post(
        "/verwaltung/anlegen",
        data={
            "anzeigename": "X",
            "email": "x@example.org",
            "benutzername": "x",
            "passwort": "geheim123",
            "rolle": "admin",
        },
    )

    assert antwort.status_code == 403
    assert _nutzer("x") is None


def test_the_admin_sets_a_role(umgebung):
    antwort = _client("u-admin").post(
        "/verwaltung/u-member/rolle", data={"rolle": "admin"}
    )

    assert antwort.status_code == 303
    assert _nutzer("u-member").role == "admin"
    assert ("u-admin", "verwaltung.rolle_gesetzt") in _protokoll()


def test_the_own_role_cannot_be_removed(umgebung):
    antwort = _client("u-admin").post(
        "/verwaltung/u-admin/rolle", data={"rolle": "member"}
    )

    assert antwort.status_code == 303
    assert _nutzer("u-admin").role == "admin"


def test_the_admin_blocks_and_releases_an_account(umgebung):
    client = _client("u-admin")

    client.post("/verwaltung/u-member/zugang", data={"aktiv": "0"})
    assert _nutzer("u-member").active is False

    client.post("/verwaltung/u-member/zugang", data={"aktiv": "1"})
    assert _nutzer("u-member").active is True
    assert ("u-admin", "verwaltung.zugang_gesetzt") in _protokoll()
