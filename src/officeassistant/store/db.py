"""Datenbankzugriff und Migrationen.

Eine einzige SQL-Datei beschreibt das Schema; sie ist idempotent und wird bei jedem
Start angewandt. Damit gibt es keinen Zustand, der nur auf einer Maschine existiert.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(db_url: str, autocommit: bool = False) -> psycopg.Connection:
    """Verbindung mit Zeilen als dict und expliziten Transaktionen.

    `autocommit=True` ist für kurzlebige Verbindungen je Werkzeugaufruf gedacht: dort
    darf ein Protokolleintrag nicht mit der Verbindung verpuffen.
    """
    return psycopg.connect(db_url, row_factory=dict_row, autocommit=autocommit)


def migrate(conn: psycopg.Connection) -> int:
    """Schema anwenden und die aktuelle Version zurückgeben."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with conn.transaction():
        conn.execute(sql)
    row = conn.execute("SELECT max(version) AS version FROM schema_version").fetchone()
    version = int(row["version"]) if row and row["version"] is not None else 0
    if version == 0:
        raise RuntimeError("Migration ohne Schema-Version beendet")
    return version


def schema_version(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT max(version) AS version FROM schema_version").fetchone()
    return int(row["version"]) if row and row["version"] is not None else 0
