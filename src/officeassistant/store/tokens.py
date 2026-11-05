"""Verschlüsselter Token-Speicher je Nutzer und Postfach.

Die Agno-Gmail-Werkzeuge legen ihr Token unter einer gemeinsamen Kennung ab; bei
mehreren Nutzern würden Postfächer vermischt. Deshalb gehören die Zugangsdaten hierher:
Schlüssel `(user_id, provider, address)`, Inhalt als Fernet-Chiffrat.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import psycopg
from cryptography.fernet import Fernet, InvalidToken

PROVIDERS = ("gmail", "graph", "imap", "fake")


class CredentialError(RuntimeError):
    """Zugangsdaten fehlen oder lassen sich nicht entschlüsseln."""


@dataclass(frozen=True, slots=True)
class Account:
    id: int
    user_id: str
    provider: str
    address: str
    status: str


class TokenStore:
    def __init__(self, conn: psycopg.Connection, token_key: str) -> None:
        self._conn = conn
        self._fernet = Fernet(token_key)

    def save(
        self,
        user_id: str,
        provider: str,
        address: str,
        payload: dict[str, Any],
        scopes: tuple[str, ...] = (),
    ) -> Account:
        if provider not in PROVIDERS:
            raise ValueError(f"Unbekannter Anbieter: {provider}")
        ciphertext = self._fernet.encrypt(json.dumps(payload).encode())
        with self._conn.transaction():
            row = self._conn.execute(
                """
                INSERT INTO mail_account (user_id, provider, address, scopes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, address) DO UPDATE
                    SET provider = excluded.provider,
                        scopes = excluded.scopes,
                        status = 'active'
                RETURNING id, user_id, provider, address, status
                """,
                (user_id, provider, address, list(scopes)),
            ).fetchone()
            self._conn.execute(
                """
                INSERT INTO credential (account_id, ciphertext)
                VALUES (%s, %s)
                ON CONFLICT (account_id) DO UPDATE
                    SET ciphertext = excluded.ciphertext,
                        updated_at = now()
                """,
                (row["id"], ciphertext),
            )
        return _account(row)

    def load(self, account_id: int) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT ciphertext FROM credential WHERE account_id = %s", (account_id,)
        ).fetchone()
        if row is None:
            raise CredentialError(f"Keine Zugangsdaten für Konto {account_id}")
        try:
            plain = self._fernet.decrypt(bytes(row["ciphertext"]))
        except InvalidToken as exc:
            raise CredentialError(
                f"Zugangsdaten für Konto {account_id} nicht entschlüsselbar "
                "(falscher OA_TOKEN_KEY?)"
            ) from exc
        return json.loads(plain.decode())

    def accounts(self, user_id: str) -> list[Account]:
        rows = self._conn.execute(
            """
            SELECT id, user_id, provider, address, status
            FROM mail_account WHERE user_id = %s ORDER BY id
            """,
            (user_id,),
        ).fetchall()
        return [_account(row) for row in rows]

    def delete(self, account_id: int) -> None:
        with self._conn.transaction():
            self._conn.execute("DELETE FROM credential WHERE account_id = %s", (account_id,))
            self._conn.execute("DELETE FROM mail_account WHERE id = %s", (account_id,))


def _account(row: dict) -> Account:
    return Account(
        id=row["id"],
        user_id=row["user_id"],
        provider=row["provider"],
        address=row["address"],
        status=row["status"],
    )
