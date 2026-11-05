"""Kennzahlen für die Startseite.

Jede Abfrage ist auf einen Nutzer beschränkt. Die Startseite darf keine fremden Läufe,
Freigaben oder Termine zeigen, auch nicht als Zahl.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from officeassistant.calendar.ics import CalendarError, termine
from officeassistant.store.connections import ConnectionError_, ConnectionStore

# Agno schreibt Zustände in Großbuchstaben.
OFFEN = "PAUSED"
FERTIG = "COMPLETED"
FEHLER = "ERROR"
ABGEBROCHEN = "CANCELLED"

STATUS_TEXT = {
    FERTIG: "fertig",
    FEHLER: "gescheitert",
    OFFEN: "wartet auf Freigabe",
    ABGEBROCHEN: "abgebrochen",
    "RUNNING": "läuft",
}


@dataclass(frozen=True, slots=True)
class Lauf:
    run_id: str
    status: str
    stand: str
    zeit: datetime
    anfang: str


@dataclass(frozen=True, slots=True)
class Tagestermin:
    titel: str
    zeit: str
    ort: str


def offene_freigaben(conn: psycopg.Connection, user_id: str) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM ai.agno_approvals WHERE user_id = %s AND status = 'pending'",
        (user_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


def letzte_laeufe(conn: psycopg.Connection, user_id: str, limit: int = 5) -> list[Lauf]:
    rows = conn.execute(
        """
        SELECT run_id, status, created_at, left(coalesce(run_data->>'content', ''), 160) AS inhalt
        FROM ai.agno_runs
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    ).fetchall()
    return [
        Lauf(
            run_id=str(row["run_id"]),
            status=str(row["status"] or ""),
            stand=STATUS_TEXT.get(str(row["status"] or ""), str(row["status"] or "")),
            zeit=datetime.fromtimestamp(int(row["created_at"]), tz=UTC),
            anfang=" ".join(str(row["inhalt"] or "").split())[:120],
        )
        for row in rows
    ]


def fehlgeschlagene_laeufe(conn: psycopg.Connection, user_id: str, stunden: int = 24) -> int:
    grenze = int((datetime.now(UTC) - timedelta(hours=stunden)).timestamp())
    row = conn.execute(
        """
        SELECT count(*) AS n FROM ai.agno_runs
        WHERE user_id = %s AND status = %s AND created_at >= %s
        """,
        (user_id, FEHLER, grenze),
    ).fetchone()
    return int(row["n"]) if row else 0


def heutige_termine(
    conn: psycopg.Connection, user_id: str, token_key: str
) -> tuple[list[Tagestermin], str]:
    """Termine des heutigen Tages aus der eingerichteten Kalenderquelle.

    Rückgabe: (Termine, Hinweis). Ist keine Quelle eingerichtet oder antwortet sie nicht,
    bleibt die Liste leer und der Hinweis nennt den Grund.
    """
    try:
        quelle = ConnectionStore(conn, token_key).one(user_id, "ics").base_url
    except (ConnectionError_, LookupError, KeyError):
        return [], "Keine Kalenderquelle eingerichtet. Tragen Sie sie unter Anbindungen ein."

    beginn = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        alle = termine(quelle, beginn, beginn + timedelta(days=1))
    except CalendarError as fehler:
        return [], str(fehler)

    ortszeit = alle[0].beginn.astimezone().tzinfo if alle else None
    ausgabe: list[Tagestermin] = []
    for termin in alle:
        beginn_lokal = termin.beginn.astimezone(ortszeit)
        if termin.ganztags:
            zeit = "ganztägig"
        else:
            zeit = f"{beginn_lokal:%H:%M}–{termin.ende.astimezone(ortszeit):%H:%M}"
        ausgabe.append(Tagestermin(titel=termin.titel, zeit=zeit, ort=termin.ort))
    if not ausgabe:
        return [], "Für heute ist kein Termin eingetragen."
    return ausgabe, ""


def routine_sorgen(conn: psycopg.Connection, user_id: str) -> list[str]:
    """Routinen, die in den letzten 24 Stunden gescheitert sind oder abgeschaltet wurden."""
    grenze = datetime.now(UTC) - timedelta(hours=24)
    rows = conn.execute(
        """
        SELECT r.name, r.enabled, max(rr.started_at) AS zuletzt, max(rr.status) AS stand
        FROM routine r
        LEFT JOIN routine_run rr ON rr.routine_id = r.id AND rr.started_at >= %s
        WHERE r.user_id = %s
        GROUP BY r.id, r.name, r.enabled
        """,
        (grenze, user_id),
    ).fetchall()

    sorgen: list[str] = []
    for row in rows:
        name = str(row["name"])
        if str(row["stand"] or "") == "failed":
            sorgen.append(f"{name}: letzter Lauf gescheitert")
        elif not bool(row["enabled"]):
            sorgen.append(f"{name}: abgeschaltet")
    return sorgen


def alle_zahlen(conn: psycopg.Connection, user_id: str, token_key: str) -> dict[str, Any]:
    """Ein Aufruf für die Startseite: alle Blöcke mit einem Satz je Block."""
    termine_heute, termin_hinweis = heutige_termine(conn, user_id, token_key)
    return {
        "freigaben": offene_freigaben(conn, user_id),
        "laeufe": letzte_laeufe(conn, user_id),
        "fehler": fehlgeschlagene_laeufe(conn, user_id),
        "termine": termine_heute,
        "termin_hinweis": termin_hinweis,
        "routinen": routine_sorgen(conn, user_id),
    }
