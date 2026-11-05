"""Postfach-Auflösung: vom angemeldeten Nutzer zum Anbieter-Adapter.

Diese Schicht ist die einzige Stelle, an der Zugangsdaten und Anbieter zusammenkommen.
Der Agent bekommt nur Werkzeuge, die hierüber gehen.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from officeassistant.agents.mail_tools import MailSession, TrustLevel
from officeassistant.providers.base import MailProvider
from officeassistant.store import db
from officeassistant.store.audit import AuditLog
from officeassistant.store.tokens import TokenStore
from officeassistant.providers.fake import FakeProvider
from officeassistant.providers.imap import ImapConfig, ImapProvider

DEFAULT_TRUST: TrustLevel = "approval-required"


class NoMailbox(RuntimeError):
    """Für diesen Nutzer ist kein Postfach eingerichtet."""


def trust_for(conn: psycopg.Connection, user_id: str, tool_name: str) -> TrustLevel:
    """Vertrauensstufe aus der Tabelle; ohne Eintrag gilt die Vorgabe."""
    row = conn.execute(
        "SELECT level FROM tool_policy WHERE user_id = %s AND tool = %s",
        (user_id, tool_name),
    ).fetchone()
    if row is None:
        return DEFAULT_TRUST
    return row["level"]  # type: ignore[return-value]


def fake_mailboxes() -> dict[int, FakeProvider]:
    """Testpostfächer je Konto; nur im Prozess, damit Tests wiederholbar bleiben."""
    return _FAKE


_FAKE: dict[int, FakeProvider] = {}


def build_provider(account: dict, tokens: TokenStore) -> MailProvider:
    """Adapter aus dem Konto bauen; Zugangsdaten kommen entschlüsselt aus dem Speicher."""
    provider = account["provider"]
    if provider == "fake":
        existing = _FAKE.get(account["id"])
        if existing is None:
            existing = FakeProvider(address=account["address"])
            _FAKE[account["id"]] = existing
        return existing
    if provider == "imap":
        payload = tokens.load(int(account["id"]))
        return ImapProvider(ImapConfig.from_tokens(account["address"], payload))
    if provider == "gmail":
        payload = tokens.load(int(account["id"]))
        return ImapProvider(ImapConfig.gmail(account["address"], payload))
    raise NotImplementedError(
        f"Anbieter '{provider}' ist noch nicht angebunden (offen: P2.1/P3.1)."
    )


def resolve_session(
    conn: psycopg.Connection, user_id: str, tool_name: str, token_key: str
) -> MailSession:
    row = conn.execute(
        """
        SELECT a.id, a.user_id, a.provider, a.address, a.status
        FROM mail_account a JOIN app_user u ON u.id = a.user_id
        WHERE a.user_id = %s AND a.status = 'active' AND u.active
        ORDER BY a.id LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise NoMailbox(f"Für {user_id} ist kein aktives Postfach eingerichtet.")
    provider = build_provider(row, TokenStore(conn, token_key))
    return MailSession(
        user_id=user_id,
        provider=provider,
        trust=trust_for(conn, user_id, tool_name),
        audit=AuditLog(conn),
    )


@dataclass(slots=True)
class SessionResolver:
    """Verdrahtung für die Agentenwerkzeuge: eine Verbindung je Aufruf."""

    db_url: str
    token_key: str

    def __call__(self, run_context) -> MailSession:
        conn = db.connect(self.db_url, autocommit=True)
        session = resolve_session(conn, run_context.user_id, "mail", self.token_key)
        session = MailSession(
            user_id=session.user_id,
            provider=session.provider,
            trust=session.trust,
            audit=session.audit,
            close=conn.close,
        )
        return session
