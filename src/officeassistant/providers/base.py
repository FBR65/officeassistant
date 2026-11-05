"""Einheitlicher Vertrag für Mail- und Kalenderanbieter.

Die Agenten sehen nie Zugangsdaten und nie einen Anbieternamen. Jeder Aufruf bekommt
den Adapter des aufrufenden Nutzers; Gmail, Microsoft Graph und IMAP sind dahinter
austauschbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MessageHeader:
    provider_id: str
    thread_id: str
    sender: str
    subject: str
    received_at: datetime
    labels: tuple[str, ...] = ()
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class Message:
    header: MessageHeader
    body_text: str
    body_html: str | None = None
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Event:
    provider_id: str
    subject: str
    start: datetime
    end: datetime
    organizer: str
    attendees: tuple[str, ...] = ()
    location: str = ""


@dataclass(frozen=True, slots=True)
class DraftRef:
    provider_id: str
    to: tuple[str, ...]
    subject: str


@dataclass(frozen=True, slots=True)
class SendResult:
    provider_id: str
    thread_id: str
    sent_at: datetime
    warnings: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class MailProvider(Protocol):
    """Vertrag für einen Postfach-Adapter eines einzelnen Nutzers."""

    @property
    def address(self) -> str: ...

    def list_folders(self) -> list[str]: ...

    def search(
        self, query: str, since: datetime | None = None, limit: int = 20
    ) -> list[MessageHeader]: ...

    def get_message(self, provider_id: str) -> Message: ...

    def list_events(self, start: datetime, end: datetime) -> list[Event]: ...

    def create_draft(
        self,
        to: tuple[str, ...],
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> DraftRef: ...

    def send_draft(self, draft_id: str) -> SendResult: ...

    def apply_label(self, provider_id: str, label: str) -> None: ...

    def mark_read(self, provider_id: str) -> None: ...

    def archive(self, provider_id: str) -> None: ...

    def delete(self, provider_id: str, permanent: bool = False) -> None: ...

    def create_event(
        self,
        subject: str,
        start: datetime,
        end: datetime,
        attendees: tuple[str, ...] = (),
        body: str = "",
    ) -> Event: ...

    def move_event(self, provider_id: str, start: datetime, end: datetime) -> Event: ...
