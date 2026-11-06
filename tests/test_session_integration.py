"""Auflösung vom Nutzer zum Postfach, gegen Postgres."""

from __future__ import annotations

import os

import psycopg
import pytest
from cryptography.fernet import Fernet

from officeassistant.agents.session import NoMailbox, resolve_session, trust_for
from officeassistant.providers.fake import FakeProvider
from officeassistant.store import db
from officeassistant.store.tokens import TokenStore
from officeassistant.store.users import UserStore

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


@pytest.fixture()
def conn() -> psycopg.Connection:
    connection = db.connect(DB_URL)
    db.migrate(connection)
    connection.execute(
        "TRUNCATE audit, tool_policy, credential, mail_account, task, routine, "
        "memory_entry, app_user RESTART IDENTITY CASCADE"
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture()
def alice(conn):
    users = UserStore(conn)
    users.upsert("alice", "alice@example.org", "Alice")
    return TokenStore(conn, Fernet.generate_key().decode())


def test_schema_allows_the_fake_provider(conn, alice):
    account = alice.save("alice", "fake", "alice@example.org", {})

    assert account.provider == "fake"
    assert db.schema_version(conn) == 7


def test_session_resolves_to_the_fake_provider(conn, alice):
    alice.save("alice", "fake", "alice@example.org", {"hinweis": "test"})

    session = resolve_session(conn, "alice", "archive_mail", Fernet.generate_key().decode())

    assert isinstance(session.provider, FakeProvider)
    assert session.user_id == "alice"
    assert session.trust == "approval-required"


def test_trust_level_comes_from_the_policy_table(conn, alice):
    alice.save("alice", "fake", "alice@example.org", {})
    conn.execute(
        "INSERT INTO tool_policy (user_id, tool, level) VALUES ('alice', 'archive_mail', "
        "'read-only')"
    )
    conn.commit()

    assert trust_for(conn, "alice", "archive_mail") == "read-only"
    assert trust_for(conn, "alice", "label_mail") == "approval-required"


def test_missing_mailbox_is_reported_in_german(conn, alice):
    with pytest.raises(NoMailbox) as err:
        resolve_session(conn, "alice", "search_mail", Fernet.generate_key().decode())

    assert "kein aktives Postfach" in str(err.value)


def test_inactive_account_is_ignored(conn, alice):
    account = alice.save("alice", "fake", "alice@example.org", {})
    conn.execute("UPDATE mail_account SET status = 'revoked' WHERE id = %s", (account.id,))
    conn.commit()

    with pytest.raises(NoMailbox):
        resolve_session(conn, "alice", "search_mail", Fernet.generate_key().decode())
