"""Sitzungen der Oberfläche serverseitig halten.

Der Browser bekommt nur eine zufällige Kennung. Die Token selbst liegen verschlüsselt in
der Datenbank. Grund: ein Cookie mit drei JWT überschreitet die Grenze von 4096 Bytes und
wird dann stillschweigend verworfen — und Zugangsdaten gehören ohnehin nicht in den Browser.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any, cast

import psycopg
from cryptography.fernet import Fernet, InvalidToken

from officeassistant.store import db

SESSION_KEY = "oa_sid"
_LIFETIME = 8 * 3600


class SessionStore:
    """Sitzungen anlegen, lesen, erneuern und löschen."""

    def __init__(self, db_url: str, token_key: str) -> None:
        self._db_url = db_url
        self._fernet = Fernet(token_key)

    def _connect(self) -> psycopg.Connection:
        return db.connect(self._db_url, autocommit=True)

    def create(
        self,
        *,
        subject: str,
        email: str,
        name: str,
        tokens: dict[str, Any],
        expires_at: float,
    ) -> str:
        sid = secrets.token_urlsafe(32)
        ciphertext = self._fernet.encrypt(json.dumps(tokens).encode("utf-8"))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO ui_session (sid, subject, email, name, tokens, expires_at, seen_at)
                VALUES (%s, %s, %s, %s, %s, to_timestamp(%s), now())
                """,
                (sid, subject, email, name, ciphertext, expires_at),
            )
        finally:
            conn.close()
        return sid

    def load(self, sid: str) -> dict[str, Any] | None:
        """Sitzung samt entschlüsselten Token liefern, sofern sie noch gilt."""
        if not sid:
            return None
        conn = self._connect()
        try:
            row = cast(
                dict[str, Any] | None,
                conn.execute(
                    """
                    SELECT subject, email, name, tokens, expires_at
                    FROM ui_session WHERE sid = %s
                    """,
                    (sid,),
                ).fetchone(),
            )
        finally:
            conn.close()
        if row is None or row["expires_at"].timestamp() < time.time():
            return None
        try:
            tokens = json.loads(self._fernet.decrypt(bytes(row["tokens"])).decode("utf-8"))
        except (InvalidToken, ValueError):
            return None
        return {
            "subject": row["subject"],
            "email": row["email"],
            "name": row["name"],
            "tokens": tokens,
        }

    def update_tokens(self, sid: str, tokens: dict[str, Any], expires_at: float) -> None:
        ciphertext = self._fernet.encrypt(json.dumps(tokens).encode("utf-8"))
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE ui_session SET tokens = %s, expires_at = to_timestamp(%s), "
                "seen_at = now() WHERE sid = %s",
                (ciphertext, time.time() + _LIFETIME, sid),
            )
        finally:
            conn.close()

    def delete(self, sid: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM ui_session WHERE sid = %s", (sid,))
        finally:
            conn.close()
