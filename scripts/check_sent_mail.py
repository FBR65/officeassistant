"""Prüft eine gesendete Nachricht im Ordner „Gesendet" und den Entwurfsordner."""

from __future__ import annotations

import imaplib
from email import message_from_bytes
from email.message import EmailMessage
from email.header import decode_header, make_header
from pathlib import Path


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
    env = _env()
    adresse = env["EMAIL_ADDRESS"]
    with imaplib.IMAP4_SSL(env.get("EMAIL_IMAP_HOST", "imap.gmail.com"), 993, timeout=30) as conn:
        conn.login(adresse, env["EMAIL_PASSWORD"])

        for ordner in ("[Gmail]/Gesendet", "Drafts"):
            typ, _ = conn.select(f'"{ordner}"', readonly=True)
            if typ != "OK":
                print(f"{ordner}: nicht vorhanden")
                continue
            typ, daten = conn.uid("search", None, 'SUBJECT "Sendetest zwei"')  # type: ignore[arg-type]
            treffer = (daten[0] or b"").split() if typ == "OK" else []
            print(f"{ordner}: {len(treffer)} Nachricht(en)")
            for uid in treffer[-1:]:
                typ, roh = conn.uid("fetch", uid.decode(), "(RFC822)")
                for teil in roh:
                    if not isinstance(teil, tuple):
                        continue
                    nachricht = message_from_bytes(teil[1])
                    print("  An:      ", nachricht.get("To"))
                    print("  Von:     ", nachricht.get("From"))
                    print("  Betreff: ", str(make_header(decode_header(nachricht.get("Subject", "")))))
                    print("  Datum:   ", nachricht.get("Date"))
                    for teil_rumpf in nachricht.walk():
                        if teil_rumpf.get_content_type() != "text/plain":
                            continue
                        if teil_rumpf.get_content_disposition() == "attachment":
                            continue
                        inhalt = teil_rumpf.get_payload(decode=True) or b""
                        text = inhalt.decode(teil_rumpf.get_content_charset() or "utf-8", "replace")
                        print("  Text:    ", text.strip().replace("\n", " ")[:160])
                        break
        conn.logout()


if __name__ == "__main__":
    main()
