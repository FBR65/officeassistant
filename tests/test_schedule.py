"""Zeitpläne in Alltagssprache: Auswahl rein, Satz raus (P4.6)."""

from __future__ import annotations

import pytest

from officeassistant.routines.schedule import ScheduleError, cron_from_choice, describe


@pytest.mark.parametrize(
    ("art", "felder", "cron"),
    [
        ("taeglich", {"uhrzeit": "07:30"}, "30 7 * * *"),
        ("taeglich", {"uhrzeit": "8:05"}, "5 8 * * *"),
        ("werktags", {"uhrzeit": "08:00"}, "0 8 * * 1-5"),
        ("wochentag", {"uhrzeit": "18:00", "wochentag": "5"}, "0 18 * * 5"),
        ("monatlich", {"uhrzeit": "09:00", "monatstag": "15"}, "0 9 15 * *"),
        ("minuten", {"abstand": "30"}, "*/30 * * * *"),
        ("stunden", {"abstand": "2"}, "0 */2 * * *"),
    ],
)
def test_choice_becomes_a_schedule(art, felder, cron):
    assert cron_from_choice(art, **felder) == cron


@pytest.mark.parametrize(
    ("art", "felder", "cron", "satz"),
    [
        ("taeglich", {"uhrzeit": "07:30"}, "30 7 * * *", "jeden Tag um 07:30"),
        ("werktags", {"uhrzeit": "08:00"}, "0 8 * * 1-5", "werktags um 08:00"),
        ("wochentag", {"uhrzeit": "18:00", "wochentag": "5"}, "0 18 * * 5", "jeden Freitag um 18:00"),
        ("monatlich", {"uhrzeit": "09:00", "monatstag": "15"}, "0 9 15 * *", "am 15. jedes Monats um 09:00"),
        ("minuten", {"abstand": "30"}, "*/30 * * * *", "alle 30 Minuten"),
        ("stunden", {"abstand": "2"}, "0 */2 * * *", "alle 2 Stunden"),
    ],
)
def test_schedule_reads_as_a_sentence(art, felder, cron, satz):
    assert describe(cron_from_choice(art, **felder)) == satz
    assert describe(cron) == satz


def test_a_missing_time_is_explained_in_german():
    with pytest.raises(ScheduleError) as fehler:
        cron_from_choice("taeglich", uhrzeit="")
    assert "HH:MM" in str(fehler.value)


def test_an_impossible_time_is_refused():
    for falsch in ("25:00", "08:60", "8 Uhr", "08"):
        with pytest.raises(ScheduleError):
            cron_from_choice("taeglich", uhrzeit=falsch)


def test_an_impossible_day_of_month_is_refused():
    with pytest.raises(ScheduleError) as fehler:
        cron_from_choice("monatlich", uhrzeit="08:00", monatstag="31")
    assert "zwischen 1 und 28" in str(fehler.value)


def test_an_impossible_interval_is_refused():
    with pytest.raises(ScheduleError) as fehler:
        cron_from_choice("minuten", abstand="1")
    assert "zwischen 5 und 720" in str(fehler.value)


def test_unknown_schedule_is_not_dressed_up():
    assert describe("0 8 * * 3,5") == "unbekannter Zeitplan (0 8 * * 3,5)"
