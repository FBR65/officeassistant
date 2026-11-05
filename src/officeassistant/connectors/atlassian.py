"""Jira und Confluence (Atlassian Cloud oder Server).

Beide nutzen dieselbe Anmeldung: E-Mail plus API-Token, Basic Auth. Der Unterschied liegt
nur in den Pfaden. Getestet gegen einen Stub; ein echter Server war nicht vorhanden.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from officeassistant.connectors.base import Connection, ConnectorError, MessageRef, Page, Ticket


def _auth(connection: Connection) -> dict[str, str]:
    benutzer = connection.secret.get("email", "")
    token = connection.secret.get("token", "")
    if not benutzer or not token:
        raise ConnectorError(
            "Für Atlassian fehlen E-Mail und API-Token. Beides unter "
            "id.atlassian.com/manage-profile/security/api-tokens anlegen."
        )
    roh = base64.b64encode(f"{benutzer}:{token}".encode()).decode()
    return {"Authorization": f"Basic {roh}", "Accept": "application/json"}


@dataclass
class JiraConnector:
    kind = "jira"
    title = "Jira"
    connection: Connection
    client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client(base_url=self.connection.base_url.rstrip("/"), timeout=15)

    def search(self, query: str, limit: int = 10) -> list[Ticket]:
        jql = query if "=" in query or "ORDER BY" in query.upper() else f'text ~ "{query}"'
        # `/rest/api/2/search` hat Atlassian abgeschaltet (Antwort 410, CHANGE-20);
        # die Suche läuft jetzt über die JQL-Schnittstelle von API 3.
        antwort = self._client().get(
            "/rest/api/3/search/jql",
            params={"jql": jql, "maxResults": limit, "fields": "summary,status,assignee"},
            headers=_auth(self.connection),
        )
        if antwort.status_code == 410:
            raise ConnectorError(
                "Jira hat die alte Suchschnittstelle abgeschaltet. Bitte die Adresse prüfen; "
                "dieser Adapter nutzt /rest/api/3/search/jql."
            )
        if antwort.status_code >= 400:
            raise ConnectorError(f"Jira antwortet mit {antwort.status_code}: {antwort.text[:200]}")
        daten = antwort.json()
        return [
            Ticket(
                key=str(eintrag.get("key", "")),
                summary=str((eintrag.get("fields") or {}).get("summary", "")),
                status=str(((eintrag.get("fields") or {}).get("status") or {}).get("name", "")),
                assignee=str(
                    (((eintrag.get("fields") or {}).get("assignee") or {}).get("displayName", ""))
                ),
            )
            for eintrag in daten.get("issues", [])
        ]

    def create(self, project: str, summary: str, description: str = "", issue_type: str = "Task") -> Ticket:
        antwort = self._client().post(
            "/rest/api/2/issue",
            headers=_auth(self.connection),
            json={
                "fields": {
                    "project": {"key": project},
                    "summary": summary,
                    "description": description,
                    "issuetype": {"name": issue_type},
                }
            },
        )
        if antwort.status_code >= 400:
            raise ConnectorError(f"Jira antwortet mit {antwort.status_code}: {antwort.text[:200]}")
        daten = antwort.json()
        return Ticket(
            key=str(daten.get("key", "")),
            summary=summary,
            status="angelegt",
            assignee="",
        )

    def post(self, message: str, channel: str = "") -> MessageRef:
        raise ConnectorError(
            "Jira kennt keine Kanäle. Zum Schreiben einen Kommentar an einem Ticket nutzen."
        )

    def comment(self, issue_key: str, text: str) -> MessageRef:
        antwort = self._client().post(
            f"/rest/api/2/issue/{issue_key}/comment",
            headers=_auth(self.connection),
            json={"body": text},
        )
        if antwort.status_code >= 400:
            raise ConnectorError(f"Jira antwortet mit {antwort.status_code}: {antwort.text[:200]}")
        return MessageRef(channel=issue_key, text=text)


@dataclass
class ConfluenceConnector:
    kind = "confluence"
    title = "Confluence"
    connection: Connection
    client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client(base_url=self.connection.base_url.rstrip("/"), timeout=15)

    def search(self, query: str, limit: int = 10) -> list[Page]:
        antwort = self._client().get(
            "/rest/api/content/search",
            params={"cql": f'text ~ "{query}"', "limit": limit},
            headers=_auth(self.connection),
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Confluence antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        daten = antwort.json()
        return [
            Page(
                id=str(eintrag.get("id", "")),
                title=str(eintrag.get("title", "")),
                url=str((eintrag.get("_links") or {}).get("webui", "")),
                excerpt=str((eintrag.get("excerpt") or "")),
            )
            for eintrag in daten.get("results", [])
        ]

    def post(self, message: str, channel: str = "") -> MessageRef:
        raise ConnectorError(
            "Confluence-Seiten werden nicht über diesen Weg angelegt; dafür fehlt eine "
            "Freigabe-Stufe mit Vorschau."
        )
