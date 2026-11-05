"""Testdatenbank getrennt halten.

Die Integrationstests leeren ihre Tabellen. Laufen sie auf derselben Datenbank wie die
Vorführung, ist das Vorführpostfach nach jedem Testlauf weg. Deshalb legt dieses Modul
die Testdatenbank bei Bedarf an und stellt sicher, dass sie nicht die Produktivdatenbank
ist.
"""

from __future__ import annotations

import os

import psycopg
import pytest

TEST_DB_URL = os.environ.get("OA_TEST_DB_URL", "")
PROD_DB_URL = os.environ.get("OA_DB_URL", "")


def _ensure_database(url: str) -> None:
    """Datenbank anlegen, falls sie fehlt (Verbindung über die Verwaltungsdatenbank)."""
    base, _, name = url.rpartition("/")
    if not name or name.split("?")[0] in {"postgres", "template1"}:
        return
    admin_url = base + "/postgres"
    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{name}"')
    except psycopg.Error as exc:  # pragma: no cover - nur bei fehlenden Rechten
        raise RuntimeError(f"Testdatenbank {name} nicht erreichbar: {exc}") from exc


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_database() -> None:
    if not TEST_DB_URL:
        return
    if PROD_DB_URL and TEST_DB_URL == PROD_DB_URL:
        raise RuntimeError(
            "OA_TEST_DB_URL zeigt auf die Produktivdatenbank. Die Tests leeren ihre "
            "Tabellen; bitte eine eigene Datenbank verwenden (z. B. .../oa_test)."
        )
    _ensure_database(TEST_DB_URL)
