"""Kalender aus einer ICS-Quelle (P4.9).

Eine Abonnement-Adresse oder eine Datei. Exchange on-prem liefert über IMAP keine Termine;
Outlook und Exchange können aber einen ICS-Feed bereitstellen. Microsoft Graph ist
vorbereitet (`connectors/graph_calendar.py`), braucht aber einen Mandanten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import recurring_ical_events
from icalendar import Calendar


class CalendarError(RuntimeError):
    """Die Quelle ist nicht lesbar; der Text nennt den Grund."""


@dataclass(frozen=True, slots=True)
class Termin:
    uid: str
    titel: str
    beginn: datetime
    ende: datetime
    ort: str = ""
    teilnehmer: tuple[str, ...] = ()
    ganztags: bool = False


def _quelle_lesen(quelle: str, timeout: int = 20) -> bytes:
    """ICS von einer Adresse oder aus einer Datei holen."""
    if quelle.startswith(("http://", "https://")):
        try:
            antwort = httpx.get(quelle, timeout=timeout, follow_redirects=True)
            antwort.raise_for_status()
        except httpx.HTTPError as fehler:
            raise CalendarError(f"Der Kalender ist nicht erreichbar: {fehler}") from fehler
        return antwort.content

    pfad = Path(quelle).expanduser()
    if not pfad.is_file():
        raise CalendarError(f"Die Kalenderdatei gibt es nicht: {pfad}")
    return pfad.read_bytes()


def _als_zeit(wert: Any) -> datetime:
    """ICS liefert Datum oder Zeit; beides wird zu einer Zeit mit Zeitzone."""
    if isinstance(wert, datetime):
        return wert.astimezone(UTC) if wert.tzinfo else wert.replace(tzinfo=UTC)
    if isinstance(wert, date):
        return datetime(wert.year, wert.month, wert.day, tzinfo=UTC)
    raise CalendarError(f"Ungültige Zeitangabe im Kalender: {wert!r}")


def termine(quelle: str, von: datetime, bis: datetime) -> list[Termin]:
    """Termine im Zeitraum, wiederkehrende eingeschlossen, nach Beginn sortiert."""
    roh = _quelle_lesen(quelle)
    try:
        kalender = Calendar.from_ical(roh)
    except ValueError as fehler:
        raise CalendarError(f"Die Kalenderdaten sind unlesbar: {fehler}") from fehler

    try:
        ereignisse = recurring_ical_events.of(kalender).between(von, bis)
    except Exception as fehler:  # noqa: BLE001 - kaputte Wiederholungsregel
        raise CalendarError(f"Die Wiederholungsregeln sind unlesbar: {fehler}") from fehler

    ergebnis: list[Termin] = []
    for ereignis in ereignisse:
        beginn = _als_zeit(ereignis.get("DTSTART").dt)
        ende_wert = ereignis.get("DTEND")
        ende = _als_zeit(ende_wert.dt) if ende_wert is not None else beginn + timedelta(hours=1)
        # Mehrere Teilnehmer liefert icalendar als Liste, einen als Einzelwert.
        roh = ereignis.get("ATTENDEE")
        werte = roh if isinstance(roh, list) else ([roh] if roh is not None else [])
        teilnehmer = tuple(
            str(wert).split(":")[-1].strip()
            for wert in werte
            if "@" in str(wert)
        )
        ergebnis.append(
            Termin(
                uid=str(ereignis.get("UID", "")),
                titel=str(ereignis.get("SUMMARY", "(ohne Titel)")),
                beginn=beginn,
                ende=ende,
                ort=str(ereignis.get("LOCATION", "")),
                teilnehmer=teilnehmer,
                ganztags=ende - beginn == timedelta(days=1) and beginn.hour == 0,
            )
        )
    ergebnis.sort(key=lambda termin: termin.beginn)
    return ergebnis


def woche(quelle: str, bezug: datetime | None = None) -> tuple[datetime, datetime, list[Termin]]:
    """Montag bis Sonntag um den Bezugstag, dazu die Termine."""
    bezug = bezug or datetime.now(UTC)
    montag = (bezug - timedelta(days=bezug.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    sonntag = montag + timedelta(days=7)
    return montag, sonntag, termine(quelle, montag, sonntag)
