"""Eine Nachricht über Gmail senden und den Versand prüfen.

Aufruf:
    uv run python scripts/send_test_mail.py frank.b.reis@gmail.com "Betreff" "Text"

Zugangsdaten aus ~/.hermes/.env. Es wird nichts davon ausgegeben.
"""

from __future__ import annotations

import imaplib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from officeassistant.providers.imap import ImapConfig, ImapProvider


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
        raise SystemExit('Aufruf: send_test_mail.py <an> ["Betreff"] ["Text"]')
    an = sys.argv[1]
    betreff = sys.argv[2] if len(sys.argv) > 2 else "Testnachricht des OfficeAssistant"
    text = (
        sys.argv[3]
        if len(sys.argv) > 3
        else (
            "Diese Nachricht hat der OfficeAssistant gesendet, um den Versandweg über "
            "IMAP/SMTP zu prüfen. Es ist keine weitere Aktion nötig.\n\n"
            f"Gesendet am {{zeitpunkt}}."
        )
    ).replace("{zeitpunkt}", datetime.now(UTC).astimezone().strftime("%d.%m.%Y %H:%M"))

    env = _env()
    adresse = env.get("EMAIL_ADDRESS", "")
    kennwort = env.get("EMAIL_PASSWORD", "")
    if not adresse or not kennwort:
        raise SystemExit("EMAIL_ADDRESS oder EMAIL_PASSWORD fehlt in ~/.hermes/.env")

    config = ImapConfig(
        address=adresse,
        host=env.get("EMAIL_IMAP_HOST", "imap.gmail.com"),
        port=993,
        user=adresse,
        password=kennwort,
        ssl=True,
        smtp_host=env.get("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        smtp_port=587,
        smtp_security="starttls",
    )
    provider = ImapProvider(config)

    entwurf = provider.create_draft(to=(an,), subject=betreff, body=text)
    print(f"Entwurf:  {entwurf.provider_id} an {an}")

    ergebnis = provider.send_draft(entwurf.provider_id)
    print(f"Gesendet: {ergebnis.sent_at.astimezone():%d.%m.%Y %H:%M:%S}")

    # Gegenprobe im Ordner „Gesendet" von Gmail.
    verbindung = imaplib.IMAP4_SSL(config.host, config.port, timeout=30)
    try:
        verbindung.login(config.user, config.password)
        for ordner in ("[Gmail]/Gesendet", "[Gmail]/Sent Mail"):
            typ, _ = verbindung.select(f'"{ordner}"', readonly=True)
            if typ != "OK":
                continue
            typ, daten = verbindung.uid("search", None, f'SUBJECT "{betreff}"')  # type: ignore[arg-type]
            treffer = (daten[0] or b"").split() if typ == "OK" else []
            print(f"Im Ordner {ordner}: {len(treffer)} Nachricht(en) mit diesem Betreff")
            if treffer:
                break
    finally:
        try:
            verbindung.logout()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    main()
