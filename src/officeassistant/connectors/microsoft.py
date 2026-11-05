"""SharePoint, OneNote und Webex.

SharePoint und OneNote laufen über Microsoft Graph. Ohne Mandant und Zustimmung eines
Administrators gibt es keine Verbindung; die Adapter sagen das und erfinden nichts.
Webex hat eine eigene REST-Schnittstelle. Auch dafür fehlt hier ein Konto.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from officeassistant.connectors.base import Connection, ConnectorError, MessageRef, Page


def _bearer(connection: Connection, dienst: str) -> dict[str, str]:
    token = connection.secret.get("access_token", "")
    if not token:
        raise ConnectorError(
            f"Für {dienst} fehlt ein Zugangstoken über Microsoft Graph. Das braucht eine "
            "App-Registrierung im Mandanten und die Zustimmung eines Administrators."
        )
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


@dataclass
class SharePointConnector:
    kind = "sharepoint"
    title = "SharePoint"
    connection: Connection
    client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client(base_url="https://graph.microsoft.com/v1.0", timeout=15)

    def search(self, query: str, limit: int = 10) -> list[Page]:
        antwort = self._client().post(
            "/search/query",
            headers=_bearer(self.connection, "SharePoint"),
            json={
                "requests": [
                    {
                        "entityTypes": ["driveItem", "listItem"],
                        "query": {"queryString": query},
                        "from": 0,
                        "size": limit,
                    }
                ]
            },
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Graph antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        treffer = []
        for block in antwort.json().get("value", []):
            for behaelter in block.get("hitsContainers", []):
                for hit in behaelter.get("hits", []):
                    treffer.append(
                        Page(
                            id=str(hit.get("hitId", "")),
                            title=str(hit.get("resource", {}).get("name", "")),
                            url=str(hit.get("webUrl", "")),
                            excerpt=str(hit.get("summary", ""))[:300],
                        )
                    )
        return treffer[:limit]

    def post(self, message: str, channel: str = "") -> MessageRef:
        raise ConnectorError("SharePoint wird hier nur gelesen.")


@dataclass
class OneNoteConnector:
    kind = "onenote"
    title = "OneNote"
    connection: Connection
    client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client(base_url="https://graph.microsoft.com/v1.0", timeout=15)

    def notebooks(self) -> list[dict[str, str]]:
        antwort = self._client().get("/me/onenote/notebooks", headers=_bearer(self.connection, "OneNote"))
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Graph antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        return [
            {"id": str(n.get("id", "")), "name": str(n.get("displayName", ""))}
            for n in antwort.json().get("value", [])
        ]

    def search(self, query: str, limit: int = 10) -> list[Page]:
        raise ConnectorError(
            "OneNote lässt sich über Graph nicht durchsuchen. Seiten einzeln lesen wäre "
            "möglich, ist aber noch nicht umgesetzt."
        )

    def post(self, message: str, channel: str = "") -> MessageRef:
        raise ConnectorError("OneNote-Seiten werden hier nicht angelegt.")


@dataclass
class WebexConnector:
    kind = "webex"
    title = "Webex"
    connection: Connection
    client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client(base_url="https://webexapis.com/v1", timeout=15)

    def _headers(self) -> dict[str, str]:
        token = self.connection.secret.get("access_token", "")
        if not token:
            raise ConnectorError(
                "Für Webex fehlt ein Zugangstoken. Es entsteht im Webex-Entwicklerbereich "
                "unter „My Webex Apps“."
            )
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def search(self, query: str, limit: int = 10) -> list[Page]:
        antwort = self._client().get("/rooms", headers=self._headers())
        if antwort.status_code >= 400:
            raise ConnectorError(f"Webex antwortet mit {antwort.status_code}: {antwort.text[:200]}")
        return [
            Page(id=str(r.get("id", "")), title=str(r.get("title", "")), url="")
            for r in antwort.json().get("items", [])
            if query.lower() in str(r.get("title", "")).lower()
        ][:limit]

    def post(self, message: str, channel: str = "") -> MessageRef:
        if not channel:
            raise ConnectorError("Für Webex wird die Kennung des Raums gebraucht.")
        antwort = self._client().post(
            "/messages", headers=self._headers(), json={"roomId": channel, "text": message}
        )
        if antwort.status_code >= 400:
            raise ConnectorError(f"Webex antwortet mit {antwort.status_code}: {antwort.text[:200]}")
        return MessageRef(channel=channel, text=message)
