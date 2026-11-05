"""P3.5: IMAP/SMTP-Adapter gegen einen echten IMAP-Server (GreenMail im Container).

Start des Servers:
    podman run -d --rm --name oa-mail -p 3025:3025 -p 3143:3143 \
      -e GREENMAIL_OPTS="-Dgreenmail.setup.test.all \
        -Dgreenmail.users=alice:alicepw@example.org,bob:bobpw@example.org" \
      docker.io/greenmail/standalone:latest
    OA_TEST_IMAP=1 uv run pytest tests/test_imap_provider.py -q
"""

from __future__ import annotations

import imaplib
import os
import smtplib
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest

from officeassistant.providers.base import MailProvider
from officeassistant.providers.imap import ImapConfig, ImapProvider, NotSupported

HOST = os.environ.get("OA_TEST_IMAP_HOST", "127.0.0.1")
IMAP_PORT = int(os.environ.get("OA_TEST_IMAP_PORT", "3143"))
SMTP_PORT = int(os.environ.get("OA_TEST_SMTP_PORT", "3025"))
USER = "alice"
PASSWORD = "alicepw"
ADDRESS = "alice@example.org"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OA_TEST_IMAP") != "1",
        reason="OA_TEST_IMAP=1 nicht gesetzt (GreenMail nicht gestartet)",
    ),
]


@pytest.fixture()
def provider() -> ImapProvider:
    return ImapProvider(
        ImapConfig(
            address=ADDRESS,
            host=HOST,
            port=IMAP_PORT,
            user=USER,
            password=PASSWORD,
            ssl=False,
            smtp_host=HOST,
            smtp_port=SMTP_PORT,
            smtp_security="none",
        )
    )


def _zustellen(betreff: str, text: str, an: str = ADDRESS) -> None:
    nachricht = EmailMessage()
    nachricht["From"] = "bob@example.org"
    nachricht["To"] = an
    nachricht["Subject"] = betreff
    nachricht.set_content(text)
    with smtplib.SMTP(HOST, SMTP_PORT, timeout=15) as client:
        client.send_message(nachricht)


def _warten(bedingung, sekunden: float = 15.0):
    ende = time.time() + sekunden
    while time.time() < ende:
        ergebnis = bedingung()
        if ergebnis:
            return ergebnis
        time.sleep(0.5)
    return bedingung()


def test_provider_satisfies_the_contract(provider):
    assert isinstance(provider, MailProvider)
    assert provider.address == ADDRESS


def test_search_and_get_message(provider):
    _zustellen("Rechnung 4711", "Bitte bis Freitag zahlen. Betrag: 120 EUR.")

    treffer = _warten(lambda: provider.search("Rechnung 4711"))
    assert treffer, "Nachricht wurde nicht gefunden"

    kopf = treffer[0]
    assert "Rechnung 4711" in kopf.subject
    assert "bob@example.org" in kopf.sender
    assert kopf.received_at.tzinfo is not None

    nachricht = provider.get_message(kopf.provider_id)
    assert "120 EUR" in nachricht.body_text
    assert "<" not in nachricht.body_text  # kein HTML im Textkörper
    assert ADDRESS in nachricht.to


def test_mark_read_sets_the_seen_flag(provider):
    _zustellen("Statusprüfung", "Nur zum Lesen.")
    kopf = _warten(lambda: provider.search("Statusprüfung"))[0]

    provider.mark_read(kopf.provider_id)

    with imaplib.IMAP4(HOST, IMAP_PORT) as conn:
        conn.login(USER, PASSWORD)
        conn.select("INBOX")
        typ, data = conn.uid("fetch", kopf.provider_id.split("|")[1], "(FLAGS)")
    assert typ == "OK"
    assert b"\\Seen" in b" ".join(data)


def test_apply_label_creates_a_folder_and_copies(provider):
    _zustellen("Etikettentest", "Bitte ablegen.")
    kopf = _warten(lambda: provider.search("Etikettentest"))[0]

    provider.apply_label(kopf.provider_id, "Steuer")

    assert "Steuer" in provider.list_folders()


def test_draft_is_created_and_only_sent_when_asked(provider):
    entwurf = provider.create_draft(
        to=("bob@example.org",), subject="Antwort auf 4711", body="Zahlung ist raus."
    )
    assert entwurf.provider_id
    assert entwurf.to == ("bob@example.org",)
    assert "Drafts" in provider.list_folders()

    # Vor dem Senden liegt nichts Neues im Postfach von bob.
    assert not provider.search("Antwort auf 4711")

    ergebnis = provider.send_draft(entwurf.provider_id)
    assert ergebnis.sent_at.tzinfo is not None

    with imaplib.IMAP4(HOST, IMAP_PORT) as conn:
        conn.login("bob", "bobpw")
        conn.select("INBOX")
        gefunden = _warten(
            lambda: conn.uid("search", None, 'SUBJECT "Antwort auf 4711"')[1][0]  # type: ignore[arg-type]
        )
    assert gefunden, "Gesendete Nachricht kam bei bob nicht an"


def test_archive_moves_the_message_out_of_the_inbox(provider):
    _zustellen("Archivtest", "Bitte weglegen.")
    kopf = _warten(lambda: provider.search("Archivtest"))[0]

    provider.archive(kopf.provider_id)

    assert "Archive" in provider.list_folders()
    assert not _warten(lambda: provider.search("Archivtest"), sekunden=3)


def test_calendar_is_reported_as_unsupported(provider):
    jetzt = datetime.now(UTC)
    with pytest.raises(NotSupported) as fehler:
        provider.list_events(jetzt, jetzt + timedelta(days=1))
    assert "Graph" in str(fehler.value)


def test_missing_credentials_are_named():
    with pytest.raises(ValueError) as fehler:
        ImapConfig.from_tokens("alice@example.org", {"host": "mail.example.org"})
    assert "user" in str(fehler.value) and "password" in str(fehler.value)
