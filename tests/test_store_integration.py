"""Integrationstests gegen Postgres.

Ohne OA_TEST_DB_URL werden sie mit Begründung übersprungen, nicht stillschweigend
als bestanden gewertet.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from cryptography.fernet import Fernet

from officeassistant.store import db
from officeassistant.store.audit import AuditLog, hash_args
from officeassistant.store.tokens import CredentialError, TokenStore
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
        "TRUNCATE audit, credential, mail_account, task, routine, memory_entry, app_user "
        "RESTART IDENTITY CASCADE"
    )
    connection.commit()
    yield connection
    connection.close()


def test_migration_is_idempotent(conn):
    first = db.migrate(conn)
    second = db.migrate(conn)

    assert first == second == 7
    assert db.schema_version(conn) == 7


def test_users_upsert_and_role_check(conn):
    store = UserStore(conn)

    created = store.upsert("u1", "alice@example.org", "Alice")
    again = store.upsert("u1", "alice@example.org", "Alice Neu")

    assert created.role == "member"
    assert again.display_name == "Alice Neu"
    assert store.require("u1").email == "alice@example.org"


def test_member_cannot_touch_foreign_data(conn):
    store = UserStore(conn)
    store.upsert("alice", "alice@example.org")
    store.upsert("bob", "bob@example.org")

    store.ensure_self("alice", "alice")
    with pytest.raises(PermissionError):
        store.ensure_self("bob", "alice")


def test_admin_may_touch_foreign_data(conn):
    store = UserStore(conn)
    store.upsert("root", "root@example.org", role="owner")

    store.ensure_self("root", "alice")


def test_unknown_user_is_rejected(conn):
    store = UserStore(conn)

    with pytest.raises(PermissionError):
        store.require("niemand")


def test_token_store_roundtrip(conn):
    users = UserStore(conn)
    users.upsert("alice", "alice@example.org")
    store = TokenStore(conn, Fernet.generate_key().decode())

    account = store.save(
        "alice",
        "gmail",
        "alice@example.org",
        {"refresh_token": "geheim", "client_id": "cid"},
        scopes=("gmail.readonly",),
    )

    assert store.load(account.id)["refresh_token"] == "geheim"
    assert [a.address for a in store.accounts("alice")] == ["alice@example.org"]

    store.delete(account.id)
    assert store.accounts("alice") == []


def test_wrong_key_is_reported_in_german(conn):
    users = UserStore(conn)
    users.upsert("alice", "alice@example.org")
    writer = TokenStore(conn, Fernet.generate_key().decode())
    account = writer.save("alice", "gmail", "alice@example.org", {"refresh_token": "x"})

    reader = TokenStore(conn, Fernet.generate_key().decode())

    with pytest.raises(CredentialError) as err:
        reader.load(account.id)
    assert "nicht entschlüsselbar" in str(err.value)


def test_audit_is_ordered_and_append_only(conn):
    log = AuditLog(conn)

    first = log.append("alice", "search", {"q": "rechnung"}, "ok")
    second = log.append("alice", "send_draft", {"draft": "d1"}, "blocked")

    entries = log.entries("alice")
    assert [entry.id for entry in entries] == [second.id, first.id]
    assert entries[0].args_hash == hash_args({"draft": "d1"})
    assert entries[1].result_code == "ok"

    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE audit SET result_code = 'manipuliert' WHERE id = %s", (first.id,))
    conn.rollback()
