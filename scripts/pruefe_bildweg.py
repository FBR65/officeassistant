"""Prüft den Weg „Bild aus einem hochgeladenen Dokument auf eine Folie" ohne Modell.

Aufruf: uv run python scripts/pruefe_bildweg.py <Dokumentnummer PDF> <Dokumentnummer Bild>
"""

from __future__ import annotations

import sys

from officeassistant.agents.mail_tools import MailSession, configure_session
from officeassistant.agents.presentation_tools import create_presentation
from officeassistant.settings import Settings
from officeassistant.store import db

NUTZER = "ae643b35-86f3-4745-9af8-7bb78b9fb3e9"


class _Postfach:
    """Nicht nötig für diesen Weg; die Bilder kommen aus der Ablage."""


def main() -> int:
    settings = Settings.load()
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        vorhandene = conn.execute(
            "SELECT id, name, pfad FROM document ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    for eintrag in vorhandene:
        print(f"Dokument {eintrag['id']}: {eintrag['name']}")

    from agno.run.base import RunContext

    kontext = RunContext(run_id="probe-1", session_id="probe-sitzung", user_id=NUTZER)
    configure_session(lambda run_context: MailSession(user_id=run_context.user_id, provider=_Postfach(), trust="read-only"))

    ergebnis = create_presentation.entrypoint(
        titel="Bildweg Probe",
        untertitel="Zwei Dokumente, ein Bild",
        folien=[
            {
                "titel": "Ausgangslage",
                "stichpunkte": ["Zwei Dokumente als Grundlage"],
                "notiz": "Kurz nennen, 30 Sekunden.",
            },
            {
                "titel": "Vorgänge je Monat",
                "stichpunkte": ["Aus dem hochgeladenen Bild"],
                "bilder": [{"dokument": 2, "beschriftung": "Vorgänge je Monat, eigene Erhebung"}],
                "notiz": "Auf die Verteilung eingehen, 60 Sekunden.",
            },
        ],
        quelle_dokumente=[1, 2],
        run_context=kontext,
    )
    print("Ergebnis:", ergebnis)
    return 0 if ergebnis.get("erstellt") else 1


if __name__ == "__main__":
    sys.exit(main())
