"""Routinen: Zeitplan, Ausführung und Ergebnisablage (P4.2 bis P4.4).

Eine Routine ist ein Satz in einfacher Sprache plus Zeitplan. Der Lauf erzeugt Text; er
sendet nichts. Was rausgehen soll, entsteht als Entwurf und braucht eine Freigabe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import psycopg

# Was eine Routine darf. Die Reihenfolge ist die Reihenfolge der Anzeige.
SCOPES = {
    "read": "Nur lesen",
    "label": "Lesen und kennzeichnen",
    "draft": "Lesen und Entwürfe schreiben",
}

# Die Vertrauensstufe folgt der Befugnis. Schreibende Werkzeuge brauchen immer eine
# Freigabe durch einen Menschen, deshalb gibt es hier kein "autonom".
TRUST_FOR_SCOPE = {
    "read": "read-only",
    "label": "approval-required",
    "draft": "approval-required",
}

ROUTINE_NAMES = {
    "morgenbriefing": "Morgenbriefing",
    "inbox-triage": "Posteingang ordnen",
    "meeting-vorbereitung": "Terminvorbereitung",
}


@dataclass(frozen=True, slots=True)
class Routine:
    id: int
    user_id: str
    name: str
    cron: str
    prompt: str
    trust: str
    enabled: bool
    scope: str = "read"


def _routine(row: dict[str, Any]) -> Routine:
    return Routine(
        id=int(row["id"]),
        user_id=str(row["user_id"]),
        name=str(row["name"]),
        cron=str(row["cron"]),
        prompt=str(row["prompt"]),
        trust=str(row["trust"]),
        enabled=bool(row["enabled"]),
        scope=str(row.get("scope", "read")),
    )


def list_routines(conn: psycopg.Connection, user_id: str) -> list[Routine]:
    rows = conn.execute(
        """
        SELECT id, user_id, name, cron, prompt, trust, enabled, scope
        FROM routine WHERE user_id = %s ORDER BY id
        """,
        (user_id,),
    ).fetchall()
    return [_routine(cast(dict[str, Any], row)) for row in rows]


def find_routine(conn: psycopg.Connection, email: str, name: str) -> Routine | None:
    """Routine über die Adresse des Nutzers und ihren Namen finden."""
    row = conn.execute(
        """
        SELECT r.id, r.user_id, r.name, r.cron, r.prompt, r.trust, r.enabled, r.scope
        FROM routine r JOIN app_user u ON u.id = r.user_id
        WHERE u.email = %s AND r.name = %s
        """,
        (email, name),
    ).fetchone()
    return None if row is None else _routine(cast(dict[str, Any], row))


def save_routine(
    conn: psycopg.Connection,
    user_id: str,
    name: str,
    cron: str,
    prompt: str,
    trust: str = "approval-required",
    scope: str = "read",
) -> Routine:
    """Routine anlegen oder ändern; der Name ist je Nutzer eindeutig."""
    _pruefe_cron(cron)
    if trust not in ("read-only", "approval-required", "autonomous"):
        raise ValueError(f"Unbekannte Vertrauensstufe: {trust}")
    if scope not in SCOPES:
        raise ValueError(f"Unbekannte Befugnis: {scope}")
    row = conn.execute(
        """
        INSERT INTO routine (user_id, name, cron, prompt, trust, scope)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, name) DO UPDATE
            SET cron = excluded.cron,
                prompt = excluded.prompt,
                trust = excluded.trust,
                scope = excluded.scope,
                enabled = true
        RETURNING id, user_id, name, cron, prompt, trust, enabled, scope
        """,
        (user_id, name, cron, prompt, trust, scope),
    ).fetchone()
    if row is None:
        raise RuntimeError("Routine konnte nicht gespeichert werden")
    return _routine(cast(dict[str, Any], row))


def set_enabled(conn: psycopg.Connection, routine_id: int, user_id: str, enabled: bool) -> None:
    """Routine an- oder abschalten; fremde Routinen bleiben unberührt."""
    conn.execute(
        "UPDATE routine SET enabled = %s WHERE id = %s AND user_id = %s",
        (enabled, routine_id, user_id),
    )


def delete_routine(conn: psycopg.Connection, routine_id: int, user_id: str) -> None:
    conn.execute("DELETE FROM routine WHERE id = %s AND user_id = %s", (routine_id, user_id))


def _pruefe_cron(ausdruck: str) -> None:
    """Fünf Felder, sonst lehnt die Oberfläche ab, bevor etwas gespeichert wird."""
    felder = ausdruck.split()
    if len(felder) != 5:
        raise ValueError(
            "Der Zeitplan braucht fünf Felder: Minute Stunde Tag Monat Wochentag "
            "(Beispiel: 0 8 * * 1-5)."
        )
    from croniter import croniter

    if not croniter.is_valid(ausdruck):
        raise ValueError(f"Der Zeitplan ist nicht gültig: {ausdruck}")


def is_due(routine: Routine, jetzt: datetime | None = None) -> bool:
    """Fällt der Lauf in die laufende Minute?"""
    from croniter import croniter

    jetzt = (jetzt or datetime.now(UTC)).replace(second=0, microsecond=0)
    vorher = jetzt - timedelta(minutes=1)
    return croniter.match(routine.cron, jetzt) and not croniter.match(routine.cron, vorher)


def start_run(conn: psycopg.Connection, routine: Routine) -> int:
    row = conn.execute(
        """
        INSERT INTO routine_run (routine_id, user_id, status)
        VALUES (%s, %s, 'running') RETURNING id
        """,
        (routine.id, routine.user_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Lauf konnte nicht angelegt werden")
    return int(cast(dict[str, Any], row)["id"])


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    output: str = "",
    error: str = "",
) -> None:
    conn.execute(
        """
        UPDATE routine_run
        SET status = %s, output = %s, error = %s, ended_at = now()
        WHERE id = %s
        """,
        (status, output, error, run_id),
    )


def last_runs(conn: psycopg.Connection, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.id, r.name, run.status, run.output, run.error, run.started_at, run.ended_at
        FROM routine_run run JOIN routine r ON r.id = run.routine_id
        WHERE run.user_id = %s
        ORDER BY run.started_at DESC LIMIT %s
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]
