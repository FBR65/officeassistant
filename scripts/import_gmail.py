"""Gmail-Postfach für einen Nutzer einrichten (App-Kennwort aus ~/.hermes/.env).

Die Zugangsdaten bleiben in der Datei; hier landen sie nur verschlüsselt in der Datenbank.
Aufruf:

    uv run python scripts/import_gmail.py alice@example.org
"""

from __future__ import annotations

import sys
from pathlib import Path

from officeassistant.settings import Settings
from officeassistant.store import db, users
from officeassistant.store.tokens import TokenStore


def _env() -> dict[str, str]:
    werte: dict[str, str] = {}
    for zeile in Path.home().joinpath(".hermes/.env").read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, wert = zeile.split("=", 1)
        if schluessel.startswith("EMAIL_"):
            werte[schluessel] = wert.strip().strip('"').strip("'")
    return werte


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Aufruf: import_gmail.py <nutzer-id-oder-adresse>")
    nutzer = sys.argv[1]

    settings = Settings.load()
    env = _env()
    adresse = env.get("EMAIL_ADDRESS", "")
    kennwort = env.get("EMAIL_PASSWORD", "")
    if not adresse or not kennwort:
        raise SystemExit("EMAIL_ADDRESS oder EMAIL_PASSWORD fehlt in ~/.hermes/.env")

    conn = db.connect(settings.db_url, autocommit=True)
    try:
        db.migrate(conn)
        zeile = conn.execute(
            "SELECT id FROM app_user WHERE id = %s OR email = %s", (nutzer, nutzer)
        ).fetchone()
        if zeile is None:
            raise SystemExit(f"Kein Nutzer {nutzer}. Zuerst anmelden, dann erneut versuchen.")
        user_id = str(zeile["id"])

        users.UserStore(conn).upsert(user_id, adresse, adresse)
        name = env.get("EMAIL_FROM_NAME", "") or "Emil Mazdarati"
        konto = TokenStore(conn, settings.token_key).save(
            user_id, "gmail", adresse, {"password": kennwort, "display_name": name}
        )
        print(f"Gmail verbunden für {user_id}: {konto.address} (Anbieter {konto.provider})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
