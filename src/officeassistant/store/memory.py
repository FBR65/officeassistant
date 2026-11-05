"""Gedächtnis je Nutzer (P4.7).

Was der Assistent über eine Person, ein Projekt oder den Schreibstil gelernt hat, steht
hier — sichtbar und löschbar. Es gilt nur für den Nutzer, der es angelegt hat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import psycopg

KINDS = {
    "person": "Person",
    "project": "Projekt",
    "voice": "Schreibstil",
    "other": "Sonstiges",
}

MAX_MERKEN = 200  # mehr Einträge werden nicht in den Auftrag gehoben


@dataclass(frozen=True, slots=True)
class Memory:
    id: int
    user_id: str
    kind: str
    text: str
    source: str


def _memory(row: dict[str, Any]) -> Memory:
    return Memory(
        id=int(row["id"]),
        user_id=str(row["user_id"]),
        kind=str(row["kind"]),
        text=str(row["text"]),
        source=str(row["source"]),
    )


def remember(
    conn: psycopg.Connection, user_id: str, text: str, kind: str = "other", source: str = "chat"
) -> Memory:
    """Einen Merksatz ablegen. Doppelte Sätze werden nicht zweimal gespeichert."""
    satz = " ".join((text or "").split())
    if not satz:
        raise ValueError("Der Merksatz ist leer.")
    if kind not in KINDS:
        raise ValueError(f"Unbekannte Art: {kind}")

    vorhanden = conn.execute(
        "SELECT id, user_id, kind, text, source FROM memory_entry "
        "WHERE user_id = %s AND lower(text) = lower(%s)",
        (user_id, satz),
    ).fetchone()
    if vorhanden is not None:
        return _memory(cast(dict[str, Any], vorhanden))

    row = conn.execute(
        """
        INSERT INTO memory_entry (user_id, kind, text, source)
        VALUES (%s, %s, %s, %s)
        RETURNING id, user_id, kind, text, source
        """,
        (user_id, kind, satz, source),
    ).fetchone()
    if row is None:
        raise RuntimeError("Merksatz konnte nicht gespeichert werden")
    return _memory(cast(dict[str, Any], row))


def entries(conn: psycopg.Connection, user_id: str) -> list[Memory]:
    rows = conn.execute(
        "SELECT id, user_id, kind, text, source FROM memory_entry "
        "WHERE user_id = %s ORDER BY id",
        (user_id,),
    ).fetchall()
    return [_memory(cast(dict[str, Any], row)) for row in rows]


def forget(conn: psycopg.Connection, memory_id: int, user_id: str) -> None:
    conn.execute(
        "DELETE FROM memory_entry WHERE id = %s AND user_id = %s", (memory_id, user_id)
    )


def as_instructions(conn: psycopg.Connection, user_id: str) -> list[str]:
    """Merksätze als Anweisungen für das Modell; leer, wenn nichts gemerkt ist."""
    alle = entries(conn, user_id)[:MAX_MERKEN]
    if not alle:
        return []
    zeilen = [f"- ({KINDS.get(eintrag.kind, eintrag.kind)}) {eintrag.text}" for eintrag in alle]
    return [
        "Was du über diesen Nutzer weißt (nur verwenden, wenn es zum Auftrag passt):",
        *zeilen,
    ]
