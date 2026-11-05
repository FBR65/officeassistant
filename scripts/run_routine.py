"""Routinen starten: von Hand oder aus einem Zeitgeber.

    uv run python scripts/run_routine.py --name morgenbriefing --user alice@example.org
    uv run python scripts/run_routine.py --due          # alles, was jetzt fällig ist

Der Zeitgeber (systemd-Timer, siehe deploy/) ruft die zweite Form jede Minute auf.
"""

from __future__ import annotations

import argparse
import sys

from officeassistant.routines.runner import due_routines, run_routine
from officeassistant.routines.store import Routine, find_routine
from officeassistant.settings import Settings
from officeassistant.store import db


def _load(settings: Settings, email: str, name: str) -> Routine:
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        routine = find_routine(conn, email, name)
    finally:
        conn.close()
    if routine is None:
        raise SystemExit(f"Keine Routine '{name}' für {email}")
    return routine


def main() -> int:
    parser = argparse.ArgumentParser(description="Routine ausführen")
    parser.add_argument("--name", help="Name der Routine")
    parser.add_argument("--user", help="Postfach-Adresse des Nutzers")
    parser.add_argument(
        "--due", action="store_true", help="alle jetzt fälligen Routinen starten"
    )
    args = parser.parse_args()

    settings = Settings.load()

    if args.due:
        conn = db.connect(settings.db_url, autocommit=True)
        try:
            faellig = due_routines(conn)
        finally:
            conn.close()
        if not faellig:
            print("Nichts fällig.")
            return 0
        for routine in faellig:
            print(f"Starte {routine.name} für {routine.user_id}")
            ergebnis = run_routine(routine, settings)
            print(f"  {ergebnis['status']}: {ergebnis.get('output') or ergebnis.get('error')}")
        return 0

    if not args.name:
        parser.error("--name oder --due angeben")
    email = args.user or "alice@example.org"
    ergebnis = run_routine(_load(settings, email, args.name), settings)
    print(ergebnis.get("output") or ergebnis.get("error") or "")
    return 0 if ergebnis["status"] in ("completed", "paused") else 1


if __name__ == "__main__":
    sys.exit(main())
