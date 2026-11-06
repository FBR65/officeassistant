"""Ablage der Präsentationen und Vorschau als Bild.

Die Datei liegt unter `data/praesentationen/<Nutzer>/`. Die Datenbank führt den Eintrag;
die Auslieferung prüft, dass die Datei dem angemeldeten Nutzer gehört.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

VORSCHAU_ORDNER = "_vorschau"


class AblageFehler(RuntimeError):
    """Die Datei fehlt oder gehört einem anderen Nutzer."""


@dataclass(frozen=True, slots=True)
class Praesentation:
    id: int
    user_id: str
    titel: str
    dateiname: str
    pfad: str
    folienzahl: int
    groesse: int
    angelegt: datetime
    vorlage: str = ""


def _sauber(text: str, laenge: int = 60) -> str:
    text = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß _-]+", "", text).strip()
    return (text or "Praesentation")[:laenge].replace(" ", "-")


def ordner(datenverzeichnis: str, user_id: str) -> Path:
    return Path(datenverzeichnis) / "praesentationen" / _sauber(user_id, 80)


def dateiname(titel: str, jetzt: datetime | None = None) -> str:
    zeit = (jetzt or datetime.now(UTC)).strftime("%Y-%m-%d-%H%M")
    return f"{zeit}-{_sauber(titel)}.pptx"


def anlegen(
    conn: psycopg.Connection,
    datenverzeichnis: str,
    user_id: str,
    titel: str,
    pfad: Path,
    folienzahl: int,
    vorlage: str = "",
) -> Praesentation:
    groesse = pfad.stat().st_size
    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO presentation (user_id, titel, dateiname, pfad, folienzahl, groesse, vorlage)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, titel, dateiname, pfad, folienzahl, groesse, vorlage, created_at
            """,
            (user_id, titel, pfad.name, str(pfad), folienzahl, groesse, vorlage),
        ).fetchone()
    return _eintrag(row) if row else _fehlt()


def _eintrag(row: dict[str, Any]) -> Praesentation:
    return Praesentation(
        id=int(row["id"]),
        user_id=str(row["user_id"]),
        titel=str(row["titel"]),
        dateiname=str(row["dateiname"]),
        pfad=str(row["pfad"]),
        folienzahl=int(row["folienzahl"]),
        groesse=int(row["groesse"]),
        angelegt=row["created_at"],
        vorlage=str(row.get("vorlage") or ""),
    )


def _fehlt() -> Praesentation:
    raise AblageFehler("Der Eintrag konnte nicht angelegt werden.")


def liste(conn: psycopg.Connection, user_id: str, limit: int = 50) -> list[Praesentation]:
    rows = conn.execute(
        """
        SELECT id, user_id, titel, dateiname, pfad, folienzahl, groesse, vorlage, created_at
        FROM presentation WHERE user_id = %s ORDER BY created_at DESC LIMIT %s
        """,
        (user_id, limit),
    ).fetchall()
    return [_eintrag(row) for row in rows]


def hole(conn: psycopg.Connection, user_id: str, kennung: int) -> Praesentation:
    row = conn.execute(
        """
        SELECT id, user_id, titel, dateiname, pfad, folienzahl, groesse, vorlage, created_at
        FROM presentation WHERE id = %s AND user_id = %s
        """,
        (kennung, user_id),
    ).fetchone()
    if row is None:
        raise AblageFehler("Diese Präsentation gehört nicht zu Ihrem Konto.")
    return _eintrag(row)


def gleiche(
    conn: psycopg.Connection, user_id: str, titel: str, folienzahl: int, minuten: int = 10
) -> Praesentation | None:
    """Sucht dieselbe Präsentation aus den letzten Minuten (Schutz vor Doppelaufruf)."""
    row = conn.execute(
        """
        SELECT id, user_id, titel, dateiname, pfad, folienzahl, groesse, vorlage, created_at
        FROM presentation
        WHERE user_id = %s AND titel = %s AND folienzahl = %s
          AND created_at > now() - make_interval(mins => %s)
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, titel, folienzahl, minuten),
    ).fetchone()
    return _eintrag(row) if row else None


def loeschen(conn: psycopg.Connection, user_id: str, kennung: int) -> None:
    eintrag = hole(conn, user_id, kennung)
    Path(eintrag.pfad).unlink(missing_ok=True)
    with conn.transaction():
        conn.execute("DELETE FROM presentation WHERE id = %s AND user_id = %s", (kennung, user_id))


def vorschau(pfad: Path, ziel_ordner: Path, hoechstens: int = 12) -> list[Path]:
    """Wandelt die Datei über PDF in Bilder. Ohne LibreOffice bleibt die Liste leer."""
    if shutil.which("soffice") is None or shutil.which("pdftoppm") is None:
        return []
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(ziel_ordner), str(pfad)],
            check=False,
            capture_output=True,
            timeout=180,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    pdf = ziel_ordner / (pfad.stem + ".pdf")
    if not pdf.is_file():
        return []

    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-r",
            "90",
            "-f",
            "1",
            "-l",
            str(hoechstens),
            str(pdf),
            str(ziel_ordner / "folie"),
        ],
        check=False,
        capture_output=True,
        timeout=180,
    )
    pdf.unlink(missing_ok=True)
    return sorted(ziel_ordner.glob("folie*.png"))
