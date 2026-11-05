"""Anhängendes Protokoll über jeden Werkzeugaufruf.

Der Akteur kommt aus dem geprüften JWT-Subjekt, nie aus der Nutzlast des Clients.
Die Tabelle weist UPDATE und DELETE per Trigger ab.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: int
    user_id: str
    tool: str
    args_hash: str
    result_code: str
    ts: datetime


def hash_args(args: dict[str, Any] | None) -> str:
    """Stabiler Fingerabdruck der Argumente, ohne Inhalte zu speichern."""
    payload = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class AuditLog:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def append(
        self,
        user_id: str,
        tool: str,
        args: dict[str, Any] | None,
        result_code: str,
    ) -> AuditEntry:
        with self._conn.transaction():
            row = self._conn.execute(
                """
                INSERT INTO audit (user_id, tool, args_hash, result_code)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, tool, args_hash, result_code, ts
                """,
                (user_id, tool, hash_args(args), result_code),
            ).fetchone()
        return AuditEntry(**row)

    def entries(self, user_id: str, limit: int = 50) -> list[AuditEntry]:
        rows = self._conn.execute(
            """
            SELECT id, user_id, tool, args_hash, result_code, ts
            FROM audit WHERE user_id = %s ORDER BY id DESC LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
        return [AuditEntry(**row) for row in rows]
