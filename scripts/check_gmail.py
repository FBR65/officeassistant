"""Prüft die Gmail-Anmeldung über IMAP mit den Zugangsdaten aus ~/.hermes/.env.

Gibt nur Anzahl und Betreffzeilen aus, niemals das Kennwort.
"""

from __future__ import annotations

import imaplib
import os
from email.header import decode_header, make_header
from pathlib import Path

from officeassistant.providers.imap import ImapConfig, ImapProvider


def env_lesen() -> dict[str, str]:
    """Nur die benötigten Zeilen lesen; die Datei bleibt sonst ungelesen."""
    werte: dict[str, str] = {}
    for zeile in Path.home().joinpath(".hermes/.env").read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, wert = zeile.split("=", 1)
        if schluessel in {"EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_IMAP_HOST", "EMAIL_SMTP_HOST"}:
            werte[schluessel] = wert.strip().strip('"').strip("'")
    return werte


def main() -> None:
    werte = env_lesen()
    fehlend = [name for name in ("EMAIL_ADDRESS", "EMAIL_PASSWORD") if not werte.get(name)]
    if fehlend:
        raise SystemExit("Es fehlen: " + ", ".join(fehlend))

    adresse = werte["EMAIL_ADDRESS"]
    host = werte.get("EMAIL_IMAP_HOST", "imap.gmail.com")
    print(f"Adresse: {adresse}")
    print(f"IMAP:    {host}:993")

    # 1) Anmeldung pur prüfen
    verbindung = imaplib.IMAP4_SSL(host, 993, timeout=30)
    try:
        verbindung.login(adresse, werte["EMAIL_PASSWORD"])
        typ, ordner = verbindung.list()
        print(f"Login:   OK, {len(ordner or [])} Ordner")
        typ, daten = verbindung.select("INBOX", readonly=True)
        print(f"INBOX:   {daten[0].decode() if daten and daten[0] else '?'} Nachrichten")
    finally:
        try:
            verbindung.logout()
        except Exception:  # noqa: BLE001
            pass

    # 2) Über den eigenen Adapter lesen
    config = ImapConfig(
        address=adresse,
        host=host,
        port=993,
        user=adresse,
        password=werte["EMAIL_PASSWORD"],
        ssl=True,
        smtp_host=werte.get("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        smtp_port=587,
        smtp_security="starttls",
    )
    provider = ImapProvider(config)
    kopfzeilen = provider.search("", limit=5)
    print(f"Adapter: {len(kopfzeilen)} Nachrichten gelesen")
    for kopf in kopfzeilen[:3]:
        betreff = str(make_header(decode_header(kopf.subject)))[:60]
        print(f"  - {betreff}  (von {kopf.sender[:40]})")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    main()
