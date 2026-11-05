"""Seite „Routinen" (P4.6): Anlegen, Abschalten, Löschen — über die echten Wege."""

from __future__ import annotations

import os
import time
from typing import cast

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from officeassistant.routines.store import list_routines
from officeassistant.store import db
from officeassistant.ui import auth, routines_page

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


@pytest.fixture()
def client(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(routines_page.SETTINGS, "db_url", DB_URL, raising=False)
    monkeypatch.setattr(routines_page.SETTINGS, "token_key", key, raising=False)

    conn = db.connect(DB_URL)
    db.migrate(conn)
    conn.execute("TRUNCATE routine_run, routine, app_user RESTART IDENTITY CASCADE")
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-editor', 'e@example.org', 'E')"
    )
    conn.commit()
    conn.close()

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    routines_page.register(app)

    @app.get("/_anmelden")
    def _anmelden(request: Request):
        sid = auth.session_store(routines_page.SETTINGS).create(
            subject="u-editor",
            email="e@example.org",
            name="E",
            tokens={"access_token": "t", "expires_at": time.time() + 300},
            expires_at=time.time() + 600,
        )
        request.session[auth.SESSION_KEY] = sid
        return {"ok": True}

    with TestClient(app, follow_redirects=False) as test_client:
        test_client.get("/_anmelden")
        yield test_client


def _routinen():
    conn = db.connect(DB_URL, autocommit=True)
    try:
        return list_routines(conn, "u-editor")
    finally:
        conn.close()


def test_a_user_creates_a_routine_with_plain_language_schedule(client):
    antwort = client.post(
        "/routinen/speichern",
        data={
            "name": "Wochenbericht",
            "art": "werktags",
            "uhrzeit": "08:00",
            "prompt": "Fasse die Woche zusammen.",
            "scope": "label",
        },
    )

    assert antwort.status_code == 303
    assert "gespeichert" in antwort.headers["location"]
    alle = _routinen()
    assert [r.name for r in alle] == ["wochenbericht"]  # Name wird kleingeschrieben
    assert alle[0].cron == "0 8 * * 1-5"
    assert alle[0].scope == "label"
    assert alle[0].trust == "approval-required"  # folgt aus der Befugnis


def test_a_custom_cron_expression_is_used(client):
    client.post(
        "/routinen/speichern",
        data={
            "name": "eigene",
            "art": "wochentag",
            "uhrzeit": "06:15",
            "wochentag": "1",
            "prompt": "Montags um 6:15.",
        },
    )

    assert _routinen()[0].cron == "15 6 * * 1"


def test_a_wrong_cron_is_refused_and_nothing_is_saved(client):
    antwort = client.post(
        "/routinen/speichern",
        data={
            "name": "kaputt",
            "art": "taeglich",
            "uhrzeit": "25:00",
            "prompt": "Geht nicht.",
        },
    )

    assert antwort.status_code == 303
    assert "HH%3AMM" in antwort.headers["location"]
    assert _routinen() == []


def test_empty_name_or_prompt_is_refused(client):
    antwort = client.post(
        "/routinen/speichern",
        data={
            "name": " ",
            "art": "werktags",
            "uhrzeit": "08:00",
            "prompt": "x",
        },
    )

    assert "d%C3%BCrfen+nicht+leer" in antwort.headers["location"].replace("%20", "+")
    assert _routinen() == []


def test_saving_the_same_name_changes_the_routine(client):
    for prompt in ("Erste Fassung.", "Zweite Fassung."):
        client.post(
            "/routinen/speichern",
            data={
                "name": "wochenbericht",
                "art": "minuten",
            "abstand": "30",
                "prompt": prompt,
            },
        )

    alle = _routinen()
    assert len(alle) == 1
    assert alle[0].prompt == "Zweite Fassung."


def test_a_routine_can_be_switched_off_and_on(client):
    client.post(
        "/routinen/speichern",
        data={
            "name": "takt",
            "art": "stunden",
            "abstand": "1",
            "prompt": "Stündlich.",
        },
    )
    routine = _routinen()[0]

    client.post(f"/routinen/{routine.id}/schalten", data={"an": "0"})
    assert _routinen()[0].enabled is False

    client.post(f"/routinen/{routine.id}/schalten", data={"an": "1"})
    assert _routinen()[0].enabled is True


def test_a_routine_can_be_deleted(client):
    client.post(
        "/routinen/speichern",
        data={
            "name": "weg",
            "art": "stunden",
            "abstand": "1",
            "prompt": "Bald gelöscht.",
        },
    )
    routine = _routinen()[0]

    antwort = client.post(f"/routinen/{routine.id}/loeschen")

    assert "gel%C3%B6scht" in antwort.headers["location"]
    assert _routinen() == []


def test_another_users_routine_stays_untouched(client):
    conn = db.connect(DB_URL, autocommit=True)
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-fremd', 'f@example.org', 'F')"
    )
    conn.execute(
        "INSERT INTO routine (user_id, name, cron, prompt) "
        "VALUES ('u-fremd', 'fremd', '0 8 * * *', 'Gehört nicht mir.')"
    )
    zeile_id = conn.execute("SELECT id FROM routine WHERE user_id = 'u-fremd'").fetchone()
    assert zeile_id is not None
    fremd_id = int(cast(dict, zeile_id)["id"])
    conn.close()

    client.post(f"/routinen/{fremd_id}/loeschen")
    client.post(f"/routinen/{fremd_id}/schalten", data={"an": "0"})

    conn = db.connect(DB_URL, autocommit=True)
    try:
        zeile = conn.execute(
            "SELECT enabled FROM routine WHERE id = %s", (fremd_id,)
        ).fetchone()
    finally:
        conn.close()
    assert zeile is not None and cast(dict, zeile)["enabled"] is True
