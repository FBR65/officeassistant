"""Anbindung des IMAP-Anbieters an die Agentenschicht (ohne Netzzugriff)."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from officeassistant.agents.session import build_provider
from officeassistant.providers.imap import ImapProvider
from officeassistant.store import db
from officeassistant.store.tokens import TokenStore

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


@pytest.fixture()
def store():
    key = Fernet.generate_key().decode()
    conn = db.connect(DB_URL)
    db.migrate(conn)
    conn.execute(
        "TRUNCATE audit, tool_policy, credential, mail_account, task, routine, "
        "memory_entry, app_user RESTART IDENTITY CASCADE"
    )
    conn.execute("INSERT INTO app_user (id, email, display_name) VALUES ('u-imap', 'a@example.org', 'A')")
    conn.commit()
    tokens = TokenStore(conn, key)
    yield tokens
    conn.close()


def test_imap_account_becomes_an_imap_provider(store):
    account = store.save(
        "u-imap",
        "imap",
        "alice@example.org",
        {"host": "mail.example.org", "user": "alice", "password": "geheim"},
    )

    provider = build_provider({"id": account.id, "provider": "imap", "address": account.address}, store)

    assert isinstance(provider, ImapProvider)
    assert provider.address == "alice@example.org"
    assert provider.config.host == "mail.example.org"
    assert provider.config.port == 993  # Vorgabe, wenn nichts angegeben ist


def test_missing_imap_credentials_name_the_field(store):
    account = store.save("u-imap", "imap", "bob@example.org", {"host": "mail.example.org"})

    with pytest.raises(ValueError) as fehler:
        build_provider({"id": account.id, "provider": "imap", "address": account.address}, store)

    assert "password" in str(fehler.value)


def test_unknown_provider_is_named(store):
    account = store.save("u-imap", "graph", "c@example.org", {})

    with pytest.raises(NotImplementedError) as fehler:
        build_provider({"id": account.id, "provider": "graph", "address": account.address}, store)

    assert "graph" in str(fehler.value)


def test_gmail_uses_the_fixed_google_servers(store):
    account = store.save(
        "u-imap", "gmail", "beispiel@gmail.com", {"password": "app-kennwort"}
    )

    provider = build_provider(
        {"id": account.id, "provider": "gmail", "address": account.address}, store
    )

    assert isinstance(provider, ImapProvider)
    assert provider.config.host == "imap.gmail.com"
    assert provider.config.port == 993
    assert provider.config.smtp_host == "smtp.gmail.com"
    assert provider.config.smtp_security == "starttls"
    assert provider.config.user == "beispiel@gmail.com"


def test_gmail_without_app_password_names_what_is_missing(store):
    account = store.save("u-imap", "gmail", "ohne@gmail.com", {})

    with pytest.raises(ValueError) as fehler:
        build_provider(
            {"id": account.id, "provider": "gmail", "address": account.address}, store
        )

    assert "App-Kennwort" in str(fehler.value)


def test_the_sender_carries_the_display_name(store):
    account = store.save(
        "u-imap",
        "gmail",
        "beispiel@gmail.com",
        {"password": "app-kennwort", "display_name": "Emil Mazdarati"},
    )

    provider = build_provider(
        {"id": account.id, "provider": "gmail", "address": account.address}, store
    )

    assert provider.config.from_header == "Emil Mazdarati <beispiel@gmail.com>"


def test_without_a_name_the_address_alone_is_used(store):
    account = store.save("u-imap", "gmail", "ohne@gmail.com", {"password": "x"})

    provider = build_provider(
        {"id": account.id, "provider": "gmail", "address": account.address}, store
    )

    assert provider.config.from_header == "ohne@gmail.com"
