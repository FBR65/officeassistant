"""Gedächtnis (P4.7): je Nutzer getrennt, sichtbar, löschbar, im Auftrag wirksam."""

from __future__ import annotations

import os

import pytest
from agno.run import RunContext

from officeassistant.store import db, memory

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


@pytest.fixture()
def conn():
    verbindung = db.connect(DB_URL, autocommit=True)
    db.migrate(verbindung)
    verbindung.execute(
        "TRUNCATE routine_run, routine, audit, tool_policy, credential, mail_account, "
        "task, memory_entry, app_user RESTART IDENTITY CASCADE"
    )
    verbindung.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES "
        "('u-a', 'a@example.org', 'A'), ('u-b', 'b@example.org', 'B')"
    )
    yield verbindung
    verbindung.close()


def test_a_fact_is_stored_for_one_user_only(conn):
    memory.remember(conn, "u-a", "Frank siezt lieber.", "voice")

    assert [eintrag.text for eintrag in memory.entries(conn, "u-a")] == ["Frank siezt lieber."]
    assert memory.entries(conn, "u-b") == []


def test_the_same_fact_is_not_stored_twice(conn):
    erst = memory.remember(conn, "u-a", "Projekt Adler läuft bis Dezember.", "project")
    zweit = memory.remember(conn, "u-a", "  Projekt   Adler läuft bis Dezember.  ", "project")

    assert erst.id == zweit.id
    assert len(memory.entries(conn, "u-a")) == 1


def test_a_fact_can_be_deleted(conn):
    eintrag = memory.remember(conn, "u-a", "Nicht mehr gültig.", "other")

    memory.forget(conn, eintrag.id, "u-a")

    assert memory.entries(conn, "u-a") == []


def test_a_foreign_user_cannot_delete_it(conn):
    eintrag = memory.remember(conn, "u-a", "Bleibt.", "other")

    memory.forget(conn, eintrag.id, "u-b")

    assert len(memory.entries(conn, "u-a")) == 1


def test_an_empty_fact_is_refused(conn):
    with pytest.raises(ValueError):
        memory.remember(conn, "u-a", "   ")


def test_memory_becomes_instructions_for_that_user(conn, monkeypatch):
    from officeassistant.agents import memory_tools

    memory.remember(conn, "u-a", "Antworten immer mit Anrede.", "voice")

    class Settings:
        db_url = DB_URL
        token_key = "x" * 44

    monkeypatch.setattr(
        memory_tools, "Settings", type("S", (), {"load": staticmethod(lambda: Settings())})
    )

    anweisungen = memory_tools.memory_instructions(
        RunContext(run_id="r", session_id="s", user_id="u-a")
    )
    fremd = memory_tools.memory_instructions(
        RunContext(run_id="r", session_id="s", user_id="u-b")
    )

    assert any("Antworten immer mit Anrede." in zeile for zeile in anweisungen)
    assert fremd == []


def test_without_a_user_there_are_no_instructions():
    from officeassistant.agents.memory_tools import memory_instructions

    assert memory_instructions(None) == []


def test_the_activity_view_counts_only_own_rows():
    """P4.8: die Ansicht filtert nach Nutzerkennung, nicht global."""
    from officeassistant.ui import activity_page

    quelle = activity_page._laeufe.__code__.co_consts
    assert any("WHERE user_id = %s" in str(t) for t in quelle), "Läufe ohne Nutzerfilter"
    quelle = activity_page._protokoll.__code__.co_consts
    assert any("WHERE user_id = %s" in str(t) for t in quelle), "Protokoll ohne Nutzerfilter"


def test_token_counts_are_read_from_the_run_data():
    from officeassistant.ui.activity_page import _token

    assert _token({"metrics": {"total_tokens": 1140}}) == "1.140"
    assert _token({"metrics": {}}) == "—"
    assert _token({}) == "—"
    assert _token(None) == "—"
