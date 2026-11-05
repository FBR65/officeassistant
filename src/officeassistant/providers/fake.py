"""In-Memory-Postfach (Testanbieter, Anbieter-Kennung `fake`).

Nur für Tests und Vorführungen: keine Netzverbindung, kein Zugangsdatum.
Im Betrieb wird dieser Anbieter nicht registriert.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from officeassistant.providers.base import (
    DraftRef,
    Event,
    Message,
    MessageHeader,
    SendResult,
)


class FakeProvider:
    """Erfüllt den MailProvider-Vertrag vollständig und ohne Seiteneffekte."""

    def __init__(self, address: str = "test@example.org") -> None:
        self._address = address
        self.messages: dict[str, Message] = {}
        self.events: dict[str, Event] = {}
        self.drafts: dict[str, DraftRef] = {}
        self.sent: list[SendResult] = []
        self.calls: list[tuple[str, tuple, dict]] = []
        self._next_id = 0
        self.seed(count=3)

    @property
    def address(self) -> str:
        return self._address

    def _id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}{self._next_id}"

    def seed(self, count: int = 3, start: datetime | None = None) -> None:
        base = start or datetime.now(UTC)
        for index in range(count):
            message_id = self._id("m")
            header = MessageHeader(
                provider_id=message_id,
                thread_id=f"t{message_id}",
                sender=f"person{index}@example.org",
                subject=f"Testnachricht {index}",
                received_at=base - timedelta(hours=index),
                labels=("INBOX",),
            )
            self.messages[message_id] = Message(
                header=header,
                body_text=f"Inhalt {index}",
                to=(self._address,),
            )

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def list_folders(self) -> list[str]:
        self._record("list_folders")
        return ["INBOX", "Gesendet", "Entwürfe"]

    def search(
        self, query: str, since: datetime | None = None, limit: int = 20
    ) -> list[MessageHeader]:
        self._record("search", query, since, limit)
        headers = [m.header for m in self.messages.values()]
        if since is not None:
            headers = [h for h in headers if h.received_at >= since]
        headers.sort(key=lambda h: h.received_at, reverse=True)
        return headers[:limit]

    def get_message(self, provider_id: str) -> Message:
        self._record("get_message", provider_id)
        return self.messages[provider_id]

    def list_events(self, start: datetime, end: datetime) -> list[Event]:
        self._record("list_events", start, end)
        return [e for e in self.events.values() if start <= e.start < end]

    def create_draft(
        self,
        to: tuple[str, ...],
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> DraftRef:
        self._record("create_draft", to, subject, body, reply_to)
        draft = DraftRef(provider_id=self._id("d"), to=to, subject=subject)
        self.drafts[draft.provider_id] = draft
        return draft

    def send_draft(self, draft_id: str) -> SendResult:
        self._record("send_draft", draft_id)
        draft = self.drafts[draft_id]
        message_id = self._id("m")
        header = MessageHeader(
            provider_id=message_id,
            thread_id=f"t{message_id}",
            sender=self._address,
            subject=draft.subject,
            received_at=datetime.now(UTC),
            labels=("SENT",),
        )
        self.messages[message_id] = Message(header=header, body_text="", to=draft.to)
        result = SendResult(
            provider_id=message_id,
            thread_id=header.thread_id,
            sent_at=header.received_at,
        )
        self.sent.append(result)
        return result

    def apply_label(self, provider_id: str, label: str) -> None:
        self._record("apply_label", provider_id, label)
        message = self.messages[provider_id]
        header = replace(message.header, labels=tuple({*message.header.labels, label}))
        self.messages[provider_id] = replace(message, header=header)

    def mark_read(self, provider_id: str) -> None:
        self._record("mark_read", provider_id)
        message = self.messages[provider_id]
        header = replace(
            message.header,
            labels=tuple(label for label in message.header.labels if label != "UNREAD"),
        )
        self.messages[provider_id] = replace(message, header=header)

    def archive(self, provider_id: str) -> None:
        self._record("archive", provider_id)
        self.apply_label(provider_id, "ARCHIVE")

    def delete(self, provider_id: str, permanent: bool = False) -> None:
        self._record("delete", provider_id, permanent)
        self.messages.pop(provider_id, None)

    def create_event(
        self,
        subject: str,
        start: datetime,
        end: datetime,
        attendees: tuple[str, ...] = (),
        body: str = "",
    ) -> Event:
        self._record("create_event", subject, start, end, attendees, body)
        event = Event(
            provider_id=self._id("e"),
            subject=subject,
            start=start,
            end=end,
            organizer=self._address,
            attendees=attendees,
        )
        self.events[event.provider_id] = event
        return event

    def move_event(self, provider_id: str, start: datetime, end: datetime) -> Event:
        self._record("move_event", provider_id, start, end)
        event = replace(self.events[provider_id], start=start, end=end)
        self.events[provider_id] = event
        return event
