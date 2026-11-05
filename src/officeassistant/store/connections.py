"""Verbindungen zu Diensten außerhalb des Postfachs je Nutzer.

Der Zugangsschlüssel liegt als Fernet-Chiffrat. Jeder Nutzer sieht nur seine Verbindungen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import psycopg
from cryptography.fernet import Fernet, InvalidToken

from officeassistant.connectors.base import Connection

# Was die Oberfläche anbietet, mit einem Satz Erklärung.
KINDS: dict[str, str] = {
    "jira": 'Jira — Vorgänge suchen, Vorgang anlegen, kommentieren',
    "confluence": "Confluence — Seiten suchen",
    "mattermost": "Mattermost — Kanäle lesen, Nachricht senden",
    "sharepoint": "SharePoint — Dateien suchen (über Microsoft Graph)",
    "onenote": "OneNote — Notizbücher lesen (über Microsoft Graph)",
    "webex": "Webex — Räume lesen, Nachricht senden",
    "ics": "Kalender — ICS-Abo oder Datei",
}

# Dienste, für die es keinen Adapter geben kann oder noch nicht gibt.
BLOCKED: dict[str, str] = {
    "skype": (
        "Skype für Unternehmen wurde am 31. Juli 2021 abgeschaltet, der Verbraucherdienst "
        "im Mai 2025. Es gibt keine Schnittstelle mehr, an die man anbinden könnte."
    ),
}


class ConnectionError_(RuntimeError):
    """Die Verbindung fehlt oder lässt sich nicht lesen."""


@dataclass(slots=True)
class ConnectionStore:
    conn: psycopg.Connection
    token_key: str
    _fernet: Fernet = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._fernet = Fernet(self.token_key)

    def save(
        self, user_id: str, kind: str, base_url: str, secret: dict[str, str], label: str = ""
    ) -> None:
        if kind in BLOCKED:
            raise ValueError(BLOCKED[kind])
        if kind not in KINDS:
            raise ValueError(f"Unbekannter Dienst: {kind}")
        chiffrat = self._fernet.encrypt(json.dumps(secret).encode("utf-8"))
        self.conn.execute(
            """
            INSERT INTO connection (user_id, kind, base_url, label, ciphertext)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, kind, base_url) DO UPDATE
                SET label = excluded.label, ciphertext = excluded.ciphertext
            """,
            (user_id, kind, base_url.rstrip("/"), label, chiffrat),
        )

    def delete(self, connection_id: int, user_id: str) -> None:
        self.conn.execute(
            "DELETE FROM connection WHERE id = %s AND user_id = %s", (connection_id, user_id)
        )

    def of_user(self, user_id: str) -> list[Connection]:
        rows = self.conn.execute(
            """
            SELECT id, user_id, kind, base_url, label, ciphertext
            FROM connection WHERE user_id = %s ORDER BY kind, id
            """,
            (user_id,),
        ).fetchall()
        ergebnis = []
        for row in rows:
            daten = cast(dict[str, Any], row)
            geheim: dict[str, str] = {}
            if daten.get("ciphertext"):
                try:
                    geheim = json.loads(self._fernet.decrypt(bytes(daten["ciphertext"])))
                except (InvalidToken, ValueError):
                    geheim = {}
            ergebnis.append(
                Connection(
                    id=int(daten["id"]),
                    user_id=str(daten["user_id"]),
                    kind=str(daten["kind"]),
                    base_url=str(daten["base_url"]),
                    label=str(daten["label"]),
                    secret=geheim,
                )
            )
        return ergebnis

    def one(self, user_id: str, kind: str) -> Connection:
        for verbindung in self.of_user(user_id):
            if verbindung.kind == kind:
                return verbindung
        raise ConnectionError_(
            f"Für {KINDS.get(kind, kind)} ist keine Verbindung eingerichtet. "
            "Sie lässt sich auf der Seite „Anbindungen“ anlegen."
        )
