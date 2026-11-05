"""Werkzeugschicht zum Postfach (P2).

Jeder Aufruf löst den angemeldeten Nutzer auf, holt sein Postfach und prüft die
Vertrauensstufe. Schreibende Werkzeuge sind zusätzlich mit einer Freigabe versehen:
der Lauf hält an, bis ein Mensch zustimmt.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Iterator, Literal

from agno.approval import approval
from agno.run.base import RunContext
from agno.tools import tool

from officeassistant.providers.base import MailProvider

TrustLevel = Literal["read-only", "approval-required", "autonomous"]

WRITE_TOOLS = ("create_draft", "send_draft", "label_mail", "archive_mail")


class ToolDenied(RuntimeError):
    """Der Nutzer hat diese Aktion für sich gesperrt."""


@dataclass(frozen=True, slots=True)
class MailSession:
    user_id: str
    provider: MailProvider
    trust: TrustLevel
    audit: Any | None = None
    close: Callable[[], None] | None = field(default=None, compare=False)


def _resolve(run_context: RunContext) -> MailSession:
    """Wird beim Start gesetzt; Tests ersetzen diese Funktion."""
    raise RuntimeError(
        "Kein Postfach aufgelöst. Ohne Verdrahtung (configure_session) darf kein "
        "Werkzeug laufen."
    )


def configure_session(resolver: Callable[[RunContext], MailSession]) -> None:
    """Verdrahtung beim Start der API setzen."""
    global _resolve
    _resolve = resolver


@contextmanager
def _session(run_context: Any) -> Iterator[MailSession]:
    """Sitzung auflösen und die zugehörige Verbindung sicher schließen."""
    if run_context is None or not getattr(run_context, "user_id", None):
        raise ToolDenied("Kein angemeldeter Nutzer am Werkzeugaufruf.")
    session = _resolve(run_context)
    try:
        yield session
    finally:
        if session.close is not None:
            session.close()


def _check_write(session: MailSession, tool_name: str) -> None:
    if session.trust == "read-only":
        raise ToolDenied(
            f"Das Postfach ist auf Lesen gestellt; '{tool_name}' ist gesperrt."
        )
    if session.audit is not None:
        session.audit.append(session.user_id, tool_name, None, "called")


def _unknown_message(message_id: str) -> str:
    """Klare Auskunft statt Ausnahme, wenn die Kennung nicht existiert."""
    return (
        f"Unbekannte Nachrichtenkennung '{message_id}'. Erst search_mail aufrufen und "
        "die Kennung aus dem Feld 'id' verwenden."
    )


def _header(header) -> dict[str, Any]:
    return {
        "id": header.provider_id,
        "thread": header.thread_id,
        "von": header.sender,
        "betreff": header.subject,
        "datum": header.received_at.isoformat(),
        "labels": list(header.labels),
        "anriss": header.snippet,
    }


@tool
def search_mail(query: str, run_context: RunContext | None = None) -> list[dict[str, Any]]:
    """Sucht Nachrichten im Postfach und gibt Kopfdaten zurück.

    Args:
        query: Suchbegriff; leer bedeutet "neueste Nachrichten".
    """
    with _session(run_context) as session:
        return [_header(header) for header in session.provider.search(query, limit=20)]


MAX_TEXT = 1500


@tool
def read_mail(
    message_id: str,
    max_zeichen: int = MAX_TEXT,
    run_context: RunContext | None = None,
) -> dict[str, Any]:
    """Liest eine Nachricht als Text.

    Args:
        message_id: Kennung aus search_mail.
        max_zeichen: Wie viel Text zurückkommt (Vorgabe 1500). Für Übersichten genügt der
            Anfang; mehr kostet Kontextfenster.
    """
    with _session(run_context) as session:
        try:
            message = session.provider.get_message(message_id)
        except KeyError:
            return {"fehler": _unknown_message(message_id)}
        # Lange Körper sprengen das Kontextfenster des Modells; der Anfang genügt für
        # Einordnung und Antwort. Der Rest bleibt im Postfach abrufbar.
        text = message.body_text
        grenze = max(200, min(int(max_zeichen), 8000))
        return {
            **_header(message.header),
            "an": list(message.to),
            "text": text[:grenze],
            "gekuerzt": len(text) > grenze,
        }


def _kalenderquelle(user_id: str) -> str:
    """Eingerichtete Kalenderquelle des Nutzers (ICS), sonst leer."""
    if not user_id:
        return ""
    try:
        from officeassistant.settings import Settings
        from officeassistant.store import db
        from officeassistant.store.connections import ConnectionError_, ConnectionStore

        settings = Settings.load()
        conn = db.connect(settings.db_url, autocommit=True)
        try:
            return ConnectionStore(conn, settings.token_key).one(user_id, "ics").base_url
        finally:
            conn.close()
    except (ConnectionError_, Exception):  # noqa: BLE001 - keine Quelle ist kein Fehler
        return ""


@tool
def list_calendar(
    days_ahead: int = 7, run_context: RunContext | None = None
) -> list[dict[str, Any]]:
    """Listet Termine ab jetzt. Nur für Fragen nach Terminen verwenden.

    Args:
        days_ahead: Anzahl der Tage ab heute. Vorgabe sieben Tage, damit auch ein Termin
            am kommenden Montag enthalten ist; für „nächste Woche" 14 setzen.
    """
    tage = max(days_ahead, 1)
    von = datetime.now(UTC)
    bis = von + timedelta(days=tage)

    quelle = _kalenderquelle(str(getattr(run_context, "user_id", "") or ""))
    if quelle:
        from officeassistant.calendar.ics import CalendarError, termine

        try:
            return [
                {
                    "titel": termin.titel,
                    # Ortszeit: der Kalender liefert UTC, der Nutzer liest Uhrzeiten
                    # Ganztägige Termine als Datum, sonst Uhrzeit in Ortszeit
                    "beginn": (
                        termin.beginn.date().isoformat()
                        if termin.ganztags
                        else termin.beginn.astimezone().isoformat(timespec="minutes")
                    ),
                    # Bei ganztägigen Terminen ist das Ende laut iCalendar der Folgetag
                    # (exklusiv); für die Auskunft ist der letzte Tag gemeint.
                    "ende": (
                        (termin.ende - timedelta(days=1)).date().isoformat()
                        if termin.ganztags
                        else termin.ende.astimezone().isoformat(timespec="minutes")
                    ),
                    "ort": termin.ort,
                    "ganztags": termin.ganztags,
                    "quelle": "Kalender (ICS)",
                }
                for termin in termine(quelle, von, bis)
            ]
        except CalendarError as fehler:
            return [{"hinweis": str(fehler)}]

    from officeassistant.providers.imap import NotSupported

    with _session(run_context) as session:
        try:
            events = session.provider.list_events(von, bis)
        except NotSupported as exc:
            # IMAP kann keinen Kalender führen. Das ist eine Auskunft, kein Absturz.
            return [{"hinweis": str(exc)}]
        return [
            {
                "titel": event.subject,
                "beginn": event.start.isoformat(),
                "ende": event.end.isoformat(),
                "ort": event.location,
            }
            for event in events
        ]


@tool(requires_confirmation=True)
@approval
def send_draft(draft_id: str, run_context: RunContext | None = None) -> str:
    """Sendet einen vorbereiteten Entwurf. Erfordert Freigabe durch einen Menschen.

    Args:
        draft_id: Kennung des Entwurfs aus create_draft.
    """
    with _session(run_context) as session:
        _check_write(session, "send_draft")
        try:
            result = session.provider.send_draft(draft_id)
        except KeyError:
            return f"Unbekannter Entwurf '{draft_id}'. Erst create_draft aufrufen."
        if session.audit is not None:
            session.audit.append(
                session.user_id, "send_draft", {"draft_id": draft_id}, "sent"
            )
        return f"Gesendet: {result.provider_id}"


@tool
def create_draft(
    to: list[str],
    subject: str,
    body: str,
    run_context: RunContext | None = None,
) -> dict[str, Any]:
    """Legt einen Entwurf an, ohne zu senden.

    Args:
        to: Empfängeradressen.
        subject: Betreff.
        body: Text des Entwurfs.
    """
    with _session(run_context) as session:
        _check_write(session, "create_draft")
        draft = session.provider.create_draft(tuple(to), subject, body)
        if session.audit is not None:
            session.audit.append(session.user_id, "create_draft", {"to": to}, "created")
        return {"id": draft.provider_id, "an": list(draft.to), "betreff": draft.subject}


@tool(requires_confirmation=True)
@approval
def label_mail(message_id: str, label: str, run_context: RunContext | None = None) -> str:
    """Vergibt ein Label an eine Nachricht.

    Args:
        message_id: Kennung der Nachricht.
        label: Name des Labels.
    """
    with _session(run_context) as session:
        _check_write(session, "label_mail")
        try:
            session.provider.apply_label(message_id, label)
        except KeyError:
            return _unknown_message(message_id)
        if session.audit is not None:
            session.audit.append(
                session.user_id, "label_mail", {"id": message_id}, "labelled"
            )
        return f"Label '{label}' gesetzt."


@tool(requires_confirmation=True)
@approval
def archive_mail(message_id: str, run_context: RunContext | None = None) -> str:
    """Archiviert eine Nachricht.

    Args:
        message_id: Kennung der Nachricht.
    """
    with _session(run_context) as session:
        _check_write(session, "archive_mail")
        try:
            session.provider.archive(message_id)
        except KeyError:
            return _unknown_message(message_id)
        if session.audit is not None:
            session.audit.append(
                session.user_id, "archive_mail", {"id": message_id}, "archived"
            )
        return "Nachricht archiviert."


MAIL_TOOLS = [
    search_mail,
    read_mail,
    list_calendar,
    create_draft,
    send_draft,
    label_mail,
    archive_mail,
]
