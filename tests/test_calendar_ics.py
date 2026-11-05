"""Kalender aus ICS: Lesen, Zeitraum, Wiederholungen, Fehlerfälle."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from officeassistant.calendar.ics import CalendarError, termine, woche

DATEI = Path(__file__).parent / "data" / "kalender.ics"


def test_week_contains_the_events_of_that_week():
    montag, sonntag, alle = woche(str(DATEI), datetime(2026, 11, 9, 12, tzinfo=UTC))

    assert montag == datetime(2026, 11, 9, tzinfo=UTC)
    assert sonntag == datetime(2026, 11, 16, tzinfo=UTC)
    titel = [termin.titel for termin in alle]
    assert "Wochenbesprechung" in titel
    assert "Betriebsausflug" in titel
    assert "Jour fixe" in titel  # wiederkehrend, fällt in diese Woche


def test_an_event_carries_time_place_and_attendees():
    _, _, alle = woche(str(DATEI), datetime(2026, 11, 9, 12, tzinfo=UTC))
    besprechung = next(termin for termin in alle if termin.titel == "Wochenbesprechung")

    assert besprechung.beginn == datetime(2026, 11, 9, 8, tzinfo=UTC)
    assert besprechung.ende == datetime(2026, 11, 9, 9, tzinfo=UTC)
    assert besprechung.ort == "Raum 4.12"
    assert set(besprechung.teilnehmer) == {"bob@example.org", "carol@example.org"}


def test_a_whole_day_event_is_recognised():
    _, _, alle = woche(str(DATEI), datetime(2026, 11, 9, 12, tzinfo=UTC))
    ausflug = next(termin for termin in alle if termin.titel == "Betriebsausflug")

    assert ausflug.ganztags is True


def test_a_repeating_event_appears_in_every_week():
    for tag in (2, 9):
        _, _, alle = woche(str(DATEI), datetime(2026, 11, tag, 12, tzinfo=UTC))
        assert any(termin.titel == "Jour fixe" for termin in alle), tag


def test_events_outside_the_window_are_not_shown():
    _, _, alle = woche(str(DATEI), datetime(2026, 12, 7, 12, tzinfo=UTC))

    assert alle == [] or all(termin.titel != "Wochenbesprechung" for termin in alle)


def test_a_missing_file_is_reported_with_its_path():
    with pytest.raises(CalendarError) as fehler:
        termine("/gibt/es/nicht.ics", datetime(2026, 11, 9, tzinfo=UTC), datetime(2026, 11, 16, tzinfo=UTC))
    assert "gibt es nicht" in str(fehler.value)


def test_broken_data_is_reported_not_swallowed(tmp_path):
    kaputt = tmp_path / "kaputt.ics"
    kaputt.write_text("BEGIN:VCALENDAR\nohne Ende", encoding="utf-8")

    with pytest.raises(CalendarError):
        termine(str(kaputt), datetime(2026, 11, 9, tzinfo=UTC), datetime(2026, 11, 16, tzinfo=UTC))


def test_the_graph_calendar_says_what_is_missing():
    from officeassistant.connectors.graph_calendar import GraphNotConfigured, termine as graph

    with pytest.raises(GraphNotConfigured) as fehler:
        graph("", datetime(2026, 11, 9, tzinfo=UTC), datetime(2026, 11, 16, tzinfo=UTC))
    assert "App-Registrierung" in str(fehler.value)
