"""Werkzeuge: hochgeladene Dokumente ansehen.

Nur lesend, nur eigene Dokumente. Der Text wird begrenzt zurückgegeben, damit das
Kontextfenster des Modells hält; ein Hinweis nennt, wie viel fehlt.
"""

from __future__ import annotations

from typing import Any

from agno.run.base import RunContext
from agno.tools import tool

from officeassistant.documents import store as dokumente
from officeassistant.store import db

MAX_ZEICHEN = 8000


def _verbindung(db_url: str):
    return db.connect(db_url, autocommit=True)


@tool
def list_documents(run_context: RunContext | None = None) -> list[dict[str, Any]]:
    """Listet die hochgeladenen Dokumente des angemeldeten Nutzers."""
    from officeassistant.settings import Settings

    settings = Settings.load()
    nutzer = str(getattr(run_context, "user_id", "") or "")
    if not nutzer:
        return [{"hinweis": "Kein angemeldeter Nutzer am Werkzeugaufruf."}]

    conn = _verbindung(settings.db_url)
    try:
        return [
            {
                "nummer": eintrag.id,
                "name": eintrag.name,
                "seiten": eintrag.seitenzahl,
                "zeichen": eintrag.zeichen,
                "seiten_per_texterkennung": eintrag.per_ocr,
                "angelegt": eintrag.angelegt.isoformat(timespec="minutes"),
            }
            for eintrag in dokumente.liste(conn, nutzer)
        ]
    finally:
        conn.close()


@tool
def read_document(
    dokument: int,
    seite: int = 0,
    max_zeichen: int = MAX_ZEICHEN,
    run_context: RunContext | None = None,
) -> dict[str, Any]:
    """Liest den Text eines hochgeladenen Dokuments.

    Args:
        dokument: Nummer aus list_documents.
        seite: Seitennummer; 0 liest alle Seiten.
        max_zeichen: Wie viel Text zurückkommt (Vorgabe 8000).
    """
    from officeassistant.settings import Settings

    settings = Settings.load()
    nutzer = str(getattr(run_context, "user_id", "") or "")
    if not nutzer:
        return {"fehler": "Kein angemeldeter Nutzer am Werkzeugaufruf."}

    conn = _verbindung(settings.db_url)
    try:
        try:
            eintrag = dokumente.hole(conn, nutzer, int(dokument))
        except dokumente.DokumentFehler as fehler:
            return {
                "fehler": str(fehler),
                "hinweis": "Prüfen Sie die Nummer mit list_documents.",
            }
        seiten = dokumente.seiten(conn, eintrag.id)
    finally:
        conn.close()

    if seite:
        seiten = [eintrag_seite for eintrag_seite in seiten if eintrag_seite.nummer == seite]
        if not seiten:
            return {"fehler": f"Seite {seite} gibt es in diesem Dokument nicht."}

    grenze = max(500, min(int(max_zeichen), 20000))
    text = "\n\n".join(
        f"--- Seite {eintrag_seite.nummer} ({eintrag_seite.verfahren}) ---\n{eintrag_seite.text}"
        for eintrag_seite in seiten
        if eintrag_seite.text
    )
    hinweise = [
        f"Seite {eintrag_seite.nummer}: {eintrag_seite.hinweis}"
        for eintrag_seite in seiten
        if eintrag_seite.verfahren == "fehler"
    ]

    ergebnis: dict[str, Any] = {
        "name": eintrag.name,
        "seiten": len(seiten),
        "text": text[:grenze],
        "gekuerzt": len(text) > grenze,
    }
    if hinweise:
        ergebnis["hinweise"] = hinweise
    return ergebnis


DOCUMENT_TOOLS = [list_documents, read_document]
