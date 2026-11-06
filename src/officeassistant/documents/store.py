"""Ablage der hochgeladenen Dokumente und ihrer Seiten."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from officeassistant.documents.reader import Gelesen


class DokumentFehler(RuntimeError):
    """Das Dokument fehlt oder gehört einem anderen Nutzer."""


@dataclass(frozen=True, slots=True)
class Dokument:
    id: int
    user_id: str
    name: str
    pfad: str
    seitenzahl: int
    zeichen: int
    per_ocr: int
    angelegt: datetime

    @property
    def groesse(self) -> int:
        pfad = Path(self.pfad)
        return pfad.stat().st_size if pfad.is_file() else 0


@dataclass(frozen=True, slots=True)
class Seite:
    nummer: int
    text: str
    verfahren: str
    hinweis: str


def ordner(datenverzeichnis: str, user_id: str) -> Path:
    sauber = re.sub(r"[^A-Za-z0-9_-]+", "_", user_id)[:80]
    return Path(datenverzeichnis) / "dokumente" / sauber


def dateiname(name: str, jetzt: datetime | None = None) -> str:
    stempel = (jetzt or datetime.now(UTC)).strftime("%Y-%m-%d-%H%M")
    rein = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name)[-60:] or "dokument"
    return f"{stempel}-{rein}"


def _dokument(row: dict[str, Any]) -> Dokument:
    return Dokument(
        id=int(row["id"]),
        user_id=str(row["user_id"]),
        name=str(row["name"]),
        pfad=str(row["pfad"]),
        seitenzahl=int(row["seitenzahl"]),
        zeichen=int(row["zeichen"]),
        per_ocr=int(row["per_ocr"]),
        angelegt=row["created_at"],
    )


def ablegen(
    conn: psycopg.Connection,
    user_id: str,
    name: str,
    pfad: Path,
    gelesen: Gelesen,
) -> Dokument:
    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO document (user_id, name, pfad, seitenzahl, zeichen, per_ocr)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, name, pfad, seitenzahl, zeichen, per_ocr, created_at
            """,
            (user_id, name, str(pfad), len(gelesen.seiten), gelesen.zeichen, gelesen.per_ocr),
        ).fetchone()
        if row is None:
            raise DokumentFehler("Das Dokument konnte nicht abgelegt werden.")
        for seite in gelesen.seiten:
            conn.execute(
                """
                INSERT INTO document_page (document_id, nummer, text, verfahren, hinweis)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (row["id"], seite.nummer, seite.text, seite.verfahren, seite.hinweis),
            )
    return _dokument(row)


def liste(conn: psycopg.Connection, user_id: str, limit: int = 50) -> list[Dokument]:
    rows = conn.execute(
        """
        SELECT id, user_id, name, pfad, seitenzahl, zeichen, per_ocr, created_at
        FROM document WHERE user_id = %s ORDER BY created_at DESC LIMIT %s
        """,
        (user_id, limit),
    ).fetchall()
    return [_dokument(row) for row in rows]


def hole(conn: psycopg.Connection, user_id: str, kennung: int) -> Dokument:
    row = conn.execute(
        """
        SELECT id, user_id, name, pfad, seitenzahl, zeichen, per_ocr, created_at
        FROM document WHERE id = %s AND user_id = %s
        """,
        (kennung, user_id),
    ).fetchone()
    if row is None:
        raise DokumentFehler("Dieses Dokument gehört nicht zu Ihrem Konto.")
    return _dokument(row)


def seiten(conn: psycopg.Connection, kennung: int) -> list[Seite]:
    rows = conn.execute(
        """
        SELECT nummer, text, verfahren, hinweis FROM document_page
        WHERE document_id = %s ORDER BY nummer
        """,
        (kennung,),
    ).fetchall()
    return [
        Seite(
            nummer=int(row["nummer"]),
            text=str(row["text"] or ""),
            verfahren=str(row["verfahren"]),
            hinweis=str(row["hinweis"] or ""),
        )
        for row in rows
    ]


def loeschen(conn: psycopg.Connection, user_id: str, kennung: int) -> None:
    eintrag = hole(conn, user_id, kennung)
    with conn.transaction():
        conn.execute("DELETE FROM document WHERE id = %s AND user_id = %s", (kennung, user_id))
    Path(eintrag.pfad).unlink(missing_ok=True)
