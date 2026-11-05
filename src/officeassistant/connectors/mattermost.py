"""Mattermost: Kanäle lesen, Nachricht senden. Getestet gegen einen Stub."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from officeassistant.connectors.base import Connection, ConnectorError, MessageRef


def _headers(connection: Connection) -> dict[str, str]:
    token = connection.secret.get("token", "")
    if not token:
        raise ConnectorError(
            "Für Mattermost fehlt der Zugangsschlüssel. Er steht in Mattermost unter "
            "Konto → Sicherheit → Persönliche Zugangsschlüssel."
        )
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


@dataclass
class MattermostConnector:
    kind = "mattermost"
    title = "Mattermost"
    connection: Connection
    client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client(
            base_url=self.connection.base_url.rstrip("/"), timeout=15
        )

    def channels(self, limit: int = 30) -> list[dict[str, str]]:
        antwort = self._client().get(
            "/api/v4/users/me/teams",
            headers=_headers(self.connection),
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Mattermost antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        teams = antwort.json() or []
        if not teams:
            return []
        team_id = str(teams[0].get("id", ""))
        antwort = self._client().get(
            f"/api/v4/users/me/teams/{team_id}/channels",
            headers=_headers(self.connection),
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Mattermost antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        return [
            {"id": str(k.get("id", "")), "name": str(k.get("name", ""))}
            for k in (antwort.json() or [])[:limit]
        ]

    def posts(self, channel_id: str, limit: int = 30) -> list[dict[str, str]]:
        """Die letzten Nachrichten eines Kanals, älteste zuerst."""
        antwort = self._client().get(
            f"/api/v4/channels/{channel_id}/posts",
            headers=_headers(self.connection),
            params={"per_page": limit},
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Mattermost antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        daten = antwort.json()
        order = daten.get("order") or []
        posts = daten.get("posts") or {}
        ergebnis = [
            {
                "id": str(posts[kennung].get("id", "")),
                "user": str(posts[kennung].get("user_id", "")),
                "text": str(posts[kennung].get("message", "")),
                "zeit": str(posts[kennung].get("create_at", "")),
            }
            for kennung in order
            if kennung in posts
        ]
        ergebnis.reverse()  # Mattermost liefert neueste zuerst
        return ergebnis

    def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        antwort = self._client().post(
            "/api/v4/teams/search",
            headers=_headers(self.connection),
            json={"term": query},
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Mattermost antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        return [
            {"id": str(t.get("id", "")), "name": str(t.get("display_name", ""))}
            for t in (antwort.json() or [])[:limit]
        ]

    def post(self, message: str, channel: str = "") -> MessageRef:
        ziel = channel or self.connection.secret.get("channel_id", "")
        if not ziel:
            raise ConnectorError(
                "Kein Kanal angegeben. Entweder einen Kanalnamen mitgeben oder in der "
                "Verbindung einen Kanal hinterlegen."
            )
        antwort = self._client().post(
            "/api/v4/posts",
            headers=_headers(self.connection),
            json={"channel_id": ziel, "message": message},
        )
        if antwort.status_code >= 400:
            raise ConnectorError(
                f"Mattermost antwortet mit {antwort.status_code}: {antwort.text[:200]}"
            )
        return MessageRef(channel=ziel, text=message)
