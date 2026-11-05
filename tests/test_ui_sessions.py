"""Tests des serverseitigen Sitzungsspeichers gegen die Testdatenbank."""

from __future__ import annotations

import os
import time

import pytest
from cryptography.fernet import Fernet

from officeassistant.store import db
from officeassistant.store.ui_sessions import SessionStore

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
KEY = Fernet.generate_key().decode()

pytestmark = [
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
    pytest.mark.integration,
]


def _store() -> SessionStore:
    return SessionStore(DB_URL, KEY)


def setup_module() -> None:
    if not DB_URL:
        return
    conn = db.connect(DB_URL)
    try:
        db.migrate(conn)
    finally:
        conn.close()


def test_schema_has_the_session_table() -> None:
    conn = db.connect(DB_URL)
    try:
        assert db.schema_version(conn) >= 3
        row = conn.execute(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_name = 'ui_session'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row["n"] == 1


def test_session_survives_a_round_trip_and_stores_tokens_encrypted() -> None:
    store = _store()
    sid = store.create(
        subject="sub-t1",
        email="alice@example.org",
        name="Alice",
        tokens={"access_token": "geheim-123", "refresh_token": "r-1", "expires_at": 123.0},
        expires_at=time.time() + 600,
    )
    try:
        geladen = store.load(sid)
        assert geladen is not None
        assert geladen["subject"] == "sub-t1"
        assert geladen["tokens"]["access_token"] == "geheim-123"

        # Klartext darf nicht in der Spalte stehen.
        conn = db.connect(DB_URL, autocommit=True)
        try:
            roh = conn.execute(
                "SELECT encode(tokens, 'escape') AS inhalt FROM ui_session WHERE sid = %s",
                (sid,),
            ).fetchone()
        finally:
            conn.close()
        assert roh is not None
        assert "geheim-123" not in str(roh["inhalt"])
    finally:
        store.delete(sid)
    assert store.load(sid) is None


def test_expired_session_is_not_returned() -> None:
    store = _store()
    sid = store.create(
        subject="sub-t2",
        email="bob@example.org",
        name="Bob",
        tokens={"access_token": "x"},
        expires_at=time.time() - 5,
    )
    try:
        assert store.load(sid) is None
    finally:
        store.delete(sid)


def test_tokens_can_be_updated() -> None:
    store = _store()
    sid = store.create(
        subject="sub-t3",
        email="c@example.org",
        name="C",
        tokens={"access_token": "alt"},
        expires_at=time.time() + 600,
    )
    try:
        store.update_tokens(sid, {"access_token": "neu"}, expires_at=time.time() + 600)
        geladen = store.load(sid)
    finally:
        store.delete(sid)
    assert geladen is not None and geladen["tokens"]["access_token"] == "neu"
