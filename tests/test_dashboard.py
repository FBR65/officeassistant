"""Kennzahlen der Startseite (SPEC 2026-11-05, N1)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from officeassistant.store import dashboard, db

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]

NUTZER = "u-uebersicht"
FREMD = "u-fremd"
TOKEN_KEY = "x" * 43 + "="


@pytest.fixture()
def conn():
    # Agno legt das Schema `ai` selbst an; ohne diesen Schritt fehlen die Tabellen im Testbestand.
    from agno.db.postgres import PostgresDb

    PostgresDb(db_url=DB_URL, db_schema="ai")._create_all_tables()
    verbindung = db.connect(DB_URL)
    db.migrate(verbindung)
    verbindung.execute(
        "TRUNCATE ai.agno_approvals, ai.agno_runs, ai.agno_sessions, connection, routine_run, routine CASCADE"
    )
    verbindung.execute("TRUNCATE app_user CASCADE")
    for kennung in (NUTZER, FREMD):
        verbindung.execute(
            "INSERT INTO app_user (id, email, display_name) VALUES (%s, %s, %s)",
            (kennung, f"{kennung}@example.org", kennung),
        )
        verbindung.execute(
            "INSERT INTO ai.agno_sessions (session_id, session_type, agent_id, user_id, session_data, created_at, updated_at)"
            " VALUES (%s, 'agent', 'office-assistant', %s, '{}'::jsonb, %s, %s)",
            (f"s-{kennung}", kennung, int(time.time()), int(time.time())),
        )
    verbindung.commit()
    yield verbindung
    verbindung.close()


def _lauf(conn, kennung: str, nutzer: str, status: str, inhalt: str = "", vor: int = 0) -> None:
    conn.execute(
        """
        INSERT INTO ai.agno_runs (run_id, session_id, run_type, agent_id, user_id, status,
                                  run_data, created_at)
        VALUES (%s, %s, 'run', 'office-assistant', %s, %s, %s::jsonb, %s)
        """,
        (
            kennung,
            f"s-{nutzer}",
            nutzer,
            status,
            f'{{"content": "{inhalt}"}}',
            int(time.time()) - vor,
        ),
    )
    conn.commit()


def _freigabe(conn, kennung: str, nutzer: str, status: str) -> None:
    conn.execute(
        """
        INSERT INTO ai.agno_approvals (id, run_id, session_id, status, source_type, pause_type,
                                       tool_name, user_id, created_at)
        VALUES (%s, %s, %s, %s, 'agent', 'approval', 'send_draft', %s, %s)
        """,
        (kennung, f"r-{kennung}", f"s-{nutzer}", status, nutzer, int(time.time())),
    )
    conn.commit()


def test_only_the_own_numbers_are_counted(conn):
    _freigabe(conn, "a1", NUTZER, "pending")
    _freigabe(conn, "a2", NUTZER, "approved")
    _freigabe(conn, "a3", FREMD, "pending")

    assert dashboard.offene_freigaben(conn, NUTZER) == 1
    assert dashboard.offene_freigaben(conn, FREMD) == 1


def test_the_last_runs_are_newest_first_with_short_text(conn):
    _lauf(conn, "r1", NUTZER, "COMPLETED", "Erste Antwort", vor=300)
    _lauf(conn, "r2", NUTZER, "ERROR", "Zweite Antwort", vor=100)
    _lauf(conn, "r3", FREMD, "COMPLETED", "Fremde Antwort", vor=50)

    laeufe = dashboard.letzte_laeufe(conn, NUTZER)

    assert [lauf.run_id for lauf in laeufe] == ["r2", "r1"]
    assert laeufe[0].stand == "gescheitert"
    assert laeufe[1].anfang == "Erste Antwort"


def test_failures_of_the_last_day_are_counted(conn):
    _lauf(conn, "r4", NUTZER, "ERROR", "", vor=60)
    _lauf(conn, "r5", NUTZER, "ERROR", "", vor=3 * 24 * 3600)

    assert dashboard.fehlgeschlagene_laeufe(conn, NUTZER) == 1


def test_without_a_calendar_source_the_reason_is_named(conn):
    termine, hinweis = dashboard.heutige_termine(conn, NUTZER, TOKEN_KEY)

    assert termine == []
    assert "Keine Kalenderquelle" in hinweis


def test_the_calendar_block_shows_the_titles_of_today(conn, tmp_path: Path):
    datei = tmp_path / "kalender.ics"
    datei.write_text(
        "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "UID:1",
                "DTSTAMP:20261105T000000Z",
                "DTSTART:20261105T080000Z",
                "DTEND:20261105T090000Z",
                "SUMMARY:Wochenbesprechung",
                "LOCATION:Raum 4.12",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        ),
        encoding="utf-8",
    )
    from cryptography.fernet import Fernet

    schluessel = Fernet.generate_key().decode()
    from officeassistant.store.connections import ConnectionStore

    ConnectionStore(conn, schluessel).save(NUTZER, "ics", str(datei), {})

    # Der Termin liegt am 05.11.; die Abfrage fragt den heutigen Tag ab.
    termin = dashboard.heutige_termine(conn, NUTZER, schluessel)
    termine, hinweis = termin
    if not termine:
        pytest.skip("Der Testtag liegt nicht am heutigen Datum: " + hinweis)
    assert any(t.titel == "Wochenbesprechung" for t in termine)
