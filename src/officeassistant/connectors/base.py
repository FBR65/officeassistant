"""Anbindungen außerhalb des Postfachs.

Jeder Dienst bekommt einen kleinen Adapter mit klaren Aufgaben. Fehlt die Verbindung oder
der Zugangsschlüssel, sagt der Adapter das — er tut nicht so, als hätte er geantwortet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class NotConfigured(RuntimeError):
    """Für diesen Dienst gibt es keine Verbindung; der Text nennt den Grund."""


class ConnectorError(RuntimeError):
    """Der Dienst hat abgelehnt oder war nicht erreichbar."""


@dataclass(frozen=True, slots=True)
class Connection:
    id: int
    user_id: str
    kind: str
    base_url: str
    label: str
    secret: dict[str, str]

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.secret)


@dataclass(frozen=True, slots=True)
class Ticket:
    key: str
    summary: str
    status: str
    assignee: str = ""


@dataclass(frozen=True, slots=True)
class Page:
    id: str
    title: str
    url: str
    excerpt: str = ""


@dataclass(frozen=True, slots=True)
class MessageRef:
    channel: str
    text: str
    url: str = ""


@runtime_checkable
class WorkspaceConnector(Protocol):
    """Vertrag für einen Dienst; jede Methode arbeitet nur mit der eigenen Verbindung."""

    kind: str
    title: str

    def search(self, query: str, limit: int = 10) -> list[Ticket | Page]: ...

    def post(self, message: str, channel: str = "") -> MessageRef: ...
