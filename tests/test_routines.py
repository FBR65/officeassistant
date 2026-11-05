"""Routinen: Zeitplan, Ablage, Lauf (P4.2 bis P4.4)."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from officeassistant.routines import store
from officeassistant.routines.runner import run_routine
from officeassistant.store import db

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
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-r', 'r@example.org', 'R')"
    )
    yield verbindung
    verbindung.close()


def test_routine_is_saved_and_found(conn):
    gespeichert = store.save_routine(
        conn, "u-r", "morgenbriefing", "0 8 * * 1-5", "Briefing bitte.", "read-only"
    )

    gefunden = store.find_routine(conn, "r@example.org", "morgenbriefing")

    assert gefunden is not None
    assert gefunden.id == gespeichert.id
    assert gefunden.cron == "0 8 * * 1-5"
    assert gefunden.trust == "read-only"
    assert gefunden.enabled is True


def test_saving_twice_updates_instead_of_duplicating(conn):
    store.save_routine(conn, "u-r", "triage", "*/30 * * * *", "Alt", "read-only")
    store.save_routine(conn, "u-r", "triage", "*/15 * * * *", "Neu", "approval-required")

    alle = store.list_routines(conn, "u-r")

    assert len(alle) == 1
    assert alle[0].cron == "*/15 * * * *"
    assert alle[0].prompt == "Neu"


def test_bad_cron_is_refused_with_a_german_message(conn):
    with pytest.raises(ValueError) as fehler:
        store.save_routine(conn, "u-r", "x", "0 8 * *", "Text")
    assert "fünf Felder" in str(fehler.value)

    with pytest.raises(ValueError) as fehler:
        store.save_routine(conn, "u-r", "x", "0 25 * * *", "Text")
    assert "nicht gültig" in str(fehler.value)


def test_is_due_matches_the_minute_only(conn):
    routine = store.save_routine(conn, "u-r", "briefing", "0 8 * * *", "Text", "read-only")

    assert store.is_due(routine, datetime(2026, 11, 5, 8, 0, tzinfo=UTC)) is True
    assert store.is_due(routine, datetime(2026, 11, 5, 8, 1, tzinfo=UTC)) is False
    assert store.is_due(routine, datetime(2026, 11, 5, 7, 59, tzinfo=UTC)) is False


def test_run_is_recorded_with_output(conn, monkeypatch):
    routine = store.save_routine(conn, "u-r", "briefing", "0 8 * * *", "Text", "read-only")

    class Antwort:
        content = "Briefing steht."
        tools: list = []

    class Agent:
        def run(self, prompt, user_id=None):
            return Antwort()

    monkeypatch.setattr(
        "officeassistant.routines.runner.build_routine_agent", lambda settings, r: Agent()
    )

    class Settings:
        db_url = DB_URL
        token_key = "x" * 44

    ergebnis = run_routine(routine, Settings())  # type: ignore[arg-type]

    assert ergebnis["status"] == "completed"
    assert ergebnis["output"] == "Briefing steht."
    laeufe = store.last_runs(conn, "u-r")
    assert laeufe and laeufe[0]["status"] == "completed"
    assert laeufe[0]["name"] == "briefing"


def test_failed_run_is_recorded_with_the_reason(conn, monkeypatch):
    routine = store.save_routine(conn, "u-r", "briefing", "0 8 * * *", "Text", "read-only")

    class Agent:
        def run(self, prompt, user_id=None):
            raise RuntimeError("Modell nicht erreichbar")

    monkeypatch.setattr(
        "officeassistant.routines.runner.build_routine_agent", lambda settings, r: Agent()
    )

    class Settings:
        db_url = DB_URL
        token_key = "x" * 44

    ergebnis = run_routine(routine, Settings())  # type: ignore[arg-type]

    assert ergebnis["status"] == "failed"
    assert "Modell nicht erreichbar" in ergebnis["error"]
    laeufe = store.last_runs(conn, "u-r")
    assert laeufe[0]["status"] == "failed"


def test_scope_is_stored_and_limits_the_tools(conn, monkeypatch):
    """Eine eigene Routine bekommt genau die Werkzeuge ihrer Befugnis, nie mehr."""
    from officeassistant.routines import runner

    routine = store.save_routine(
        conn, "u-r", "eigene", "0 8 * * *", "Fasse zusammen.", "read-only", "draft"
    )
    assert routine.scope == "draft"

    gesetzt = {}

    class Agent:
        def __init__(self, tools):
            self.tools = tools

        def run(self, prompt, user_id=None):
            gesetzt["tools"] = {tool.name for tool in self.tools}

            class Antwort:
                content = "ok"
                tools: list = []

            return Antwort()

    monkeypatch.setattr(
        runner,
        "build_routine_agent",
        lambda settings, r: Agent(runner._tools(r)),
    )

    class Settings:
        db_url = DB_URL
        token_key = "x" * 44

    runner.run_routine(routine, Settings())  # type: ignore[arg-type]

    assert gesetzt["tools"] == {"search_mail", "read_mail", "create_draft"}
    assert "send_draft" not in gesetzt["tools"]


def test_every_scope_excludes_sending():
    from officeassistant.routines.runner import WERKZEUGE

    for scope, tools in WERKZEUGE.items():
        namen = {tool.name for tool in tools}
        assert "send_draft" not in namen, scope


def test_unknown_scope_is_refused(conn):
    with pytest.raises(ValueError) as fehler:
        store.save_routine(conn, "u-r", "x", "0 8 * * *", "Text", "read-only", "alles")
    assert "Befugnis" in str(fehler.value)
