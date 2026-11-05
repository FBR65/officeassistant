"""Werkzeuge für die Dienste außerhalb des Postfachs.

Jedes Werkzeug nimmt die Verbindung des angemeldeten Nutzers. Fehlt sie, antwortet das
Werkzeug mit einem Satz statt mit einem Absturz oder einer erfundenen Auskunft.
"""

from __future__ import annotations

import httpx
from agno.run import RunContext
from agno.tools import tool

from officeassistant.connectors.atlassian import ConfluenceConnector, JiraConnector
from officeassistant.connectors.base import ConnectorError
from officeassistant.connectors.mattermost import MattermostConnector
from officeassistant.connectors.microsoft import (
    OneNoteConnector,
    SharePointConnector,
    WebexConnector,
)
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.connections import ConnectionError_, ConnectionStore


def _connection(run_context: RunContext | None, kind: str):
    if run_context is None or not getattr(run_context, "user_id", None):
        raise ConnectionError_("Kein angemeldeter Nutzer am Werkzeugaufruf.")
    settings = Settings.load()
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        return ConnectionStore(conn, settings.token_key).one(str(run_context.user_id), kind)
    finally:
        conn.close()


def _sauber(fehler: Exception) -> dict:
    """Fehler als Auskunft zurückgeben, damit das Modell nichts erfindet."""
    if isinstance(fehler, httpx.HTTPError):
        return {
            "fehler": "Der Dienst ist nicht erreichbar oder hat abgelehnt: "
            f"{type(fehler).__name__}: {fehler}",
            "hinweis": "Prüfen Sie Adresse und Zugangsschlüssel auf der Seite Anbindungen.",
        }
    return {"fehler": str(fehler)}


@tool
def search_jira(query: str, run_context: RunContext | None = None) -> list[dict]:
    """Sucht Vorgänge in Jira.

    Args:
        query: Freitext oder eine JQL-Abfrage.
    """
    try:
        verbindung = _connection(run_context, "jira")
        treffer = JiraConnector(verbindung).search(query)
    except (ConnectionError_, ConnectorError, httpx.HTTPError) as fehler:
        return [_sauber(fehler)]
    return [
        {"schluessel": t.key, "titel": t.summary, "stand": t.status, "bearbeiter": t.assignee}
        for t in treffer
    ]


@tool
def search_confluence(query: str, run_context: RunContext | None = None) -> list[dict]:
    """Sucht Seiten in Confluence.

    Args:
        query: Suchbegriff.
    """
    try:
        verbindung = _connection(run_context, "confluence")
        treffer = ConfluenceConnector(verbindung).search(query)
    except (ConnectionError_, ConnectorError, httpx.HTTPError) as fehler:
        return [_sauber(fehler)]
    return [{"titel": p.title, "verweis": p.url, "anriss": p.excerpt[:200]} for p in treffer]


@tool
def search_sharepoint(query: str, run_context: RunContext | None = None) -> list[dict]:
    """Sucht Dateien und Listeneinträge in SharePoint.

    Args:
        query: Suchbegriff.
    """
    try:
        verbindung = _connection(run_context, "sharepoint")
        treffer = SharePointConnector(verbindung).search(query)
    except (ConnectionError_, ConnectorError, httpx.HTTPError) as fehler:
        return [_sauber(fehler)]
    return [{"titel": p.title, "verweis": p.url, "anriss": p.excerpt[:200]} for p in treffer]


@tool
def search_onenote(query: str, run_context: RunContext | None = None) -> list[dict]:
    """Sucht in OneNote.

    Args:
        query: Suchbegriff.
    """
    try:
        verbindung = _connection(run_context, "onenote")
        OneNoteConnector(verbindung).search(query)
    except (ConnectionError_, ConnectorError, httpx.HTTPError) as fehler:
        return [_sauber(fehler)]
    return []


@tool
def search_webex(query: str, run_context: RunContext | None = None) -> list[dict]:
    """Sucht Webex-Räume.

    Args:
        query: Suchbegriff.
    """
    try:
        verbindung = _connection(run_context, "webex")
        treffer = WebexConnector(verbindung).search(query)
    except (ConnectionError_, ConnectorError, httpx.HTTPError) as fehler:
        return [_sauber(fehler)]
    return [{"raum": p.title, "kennung": p.id} for p in treffer]


CONNECTOR_TOOLS = [
    search_jira,
    search_confluence,
    search_sharepoint,
    search_onenote,
    search_webex,
]
