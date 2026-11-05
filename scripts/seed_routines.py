"""Die drei Routinen aus Q6 für einen Nutzer anlegen (Morgenbriefing, Triage, Termine)."""

from __future__ import annotations

import sys
from typing import cast

from officeassistant.routines.store import TRUST_FOR_SCOPE, save_routine
from officeassistant.settings import Settings
from officeassistant.store import db

VORGABEN = [
    (
        "morgenbriefing",
        "0 8 * * 1-5",
        "Erstelle das Morgenbriefing: Termine des Tages, Nachrichten mit Entscheidungsbedarf, "
        "offene Aufgaben.",
        "read-only",
        "read",
    ),
    (
        "inbox-triage",
        "*/30 7-19 * * 1-5",
        "Ordne den Posteingang und kennzeichne, was eine Frist hat.",
        "approval-required",
        "label",
    ),
    (
        "meeting-vorbereitung",
        "*/10 7-19 * * 1-5",
        "Bereite die Termine der nächsten zwei Stunden vor.",
        "read-only",
        "read",
    ),
]


def main() -> None:
    settings = Settings.load()
    email = sys.argv[1] if len(sys.argv) > 1 else "alice@example.org"
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        db.migrate(conn)
        row = conn.execute("SELECT id FROM app_user WHERE email = %s", (email,)).fetchone()
        if row is None:
            raise SystemExit(f"Kein Nutzer mit {email}")
        user_id = str(cast(dict, row)["id"])
        for name, cron, prompt, _trust, scope in VORGABEN:
            routine = save_routine(
                conn, user_id, name, cron, prompt, TRUST_FOR_SCOPE[scope], scope
            )
            print(f"{routine.name:22} {routine.cron:16} {routine.trust:18} {routine.scope}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
