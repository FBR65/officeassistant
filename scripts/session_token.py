"""Zugangstoken der jüngsten Sitzung ausgeben (nur für lokale Prüfungen).

Die Oberfläche legt die Token serverseitig ab; für Prüfungen ohne Browser ist das der
einfachste Weg an ein gültiges Token. Gibt nur das Token aus, keine Kennung.
"""

from __future__ import annotations

import sys

from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.ui_sessions import SessionStore


def main() -> None:
    settings = Settings.load()
    email = sys.argv[1] if len(sys.argv) > 1 else "alice@example.org"
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        row = conn.execute(
            """
            SELECT sid FROM ui_session
            WHERE email = %s AND expires_at > now()
            ORDER BY seen_at DESC LIMIT 1
            """,
            (email,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise SystemExit(f"Keine gültige Sitzung für {email}")
    data = SessionStore(settings.db_url, settings.token_key).load(row["sid"])
    if data is None:
        raise SystemExit("Sitzung nicht lesbar")
    print(data["tokens"].get("access_token", ""))


if __name__ == "__main__":
    main()
