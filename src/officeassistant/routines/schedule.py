"""Zeitpläne in Alltagssprache (P4.6).

Niemand muss hier einen Cron-Ausdruck schreiben. Der Nutzer wählt, wie oft und wann; diese
Schicht übersetzt in das Format, das der Zeitgeber versteht, und wieder zurück in einen Satz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WOCHENTAGE = [
    ("1", "Montag"),
    ("2", "Dienstag"),
    ("3", "Mittwoch"),
    ("4", "Donnerstag"),
    ("5", "Freitag"),
    ("6", "Samstag"),
    ("0", "Sonntag"),
]

ARTEN = [
    ("taeglich", "Jeden Tag"),
    ("werktags", "Werktags (Montag bis Freitag)"),
    ("wochentag", "An einem Wochentag"),
    ("monatlich", "Einmal im Monat"),
    ("minuten", "Alle … Minuten"),
    ("stunden", "Alle … Stunden"),
]

_UHRZEIT = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    """Die Angabe ergibt keinen Zeitplan; der Text ist für Nutzer gedacht."""


def _uhrzeit(text: str) -> tuple[int, int]:
    treffer = _UHRZEIT.match((text or "").strip())
    if treffer is None:
        raise ScheduleError("Bitte die Uhrzeit als HH:MM angeben, zum Beispiel 08:00.")
    return int(treffer.group(1)), int(treffer.group(2))


def _zahl(text: str, name: str, unten: int, oben: int) -> int:
    wert = (text or "").strip()
    if not wert.isdigit():
        raise ScheduleError(f"Bitte für {name} eine Zahl eintragen.")
    zahl = int(wert)
    if not unten <= zahl <= oben:
        raise ScheduleError(f"{name} muss zwischen {unten} und {oben} liegen.")
    return zahl


def cron_from_choice(
    art: str,
    uhrzeit: str = "",
    wochentag: str = "1",
    monatstag: str = "1",
    abstand: str = "",
) -> str:
    """Aus der Auswahl des Nutzers einen Zeitplan bauen."""
    if art == "taeglich":
        stunde, minute = _uhrzeit(uhrzeit)
        return f"{minute} {stunde} * * *"

    if art == "werktags":
        stunde, minute = _uhrzeit(uhrzeit)
        return f"{minute} {stunde} * * 1-5"

    if art == "wochentag":
        stunde, minute = _uhrzeit(uhrzeit)
        tag = str(wochentag).strip()
        if tag not in {wert for wert, _label in WOCHENTAGE}:
            raise ScheduleError("Bitte einen Wochentag auswählen.")
        return f"{minute} {stunde} * * {tag}"

    if art == "monatlich":
        stunde, minute = _uhrzeit(uhrzeit)
        tag = _zahl(monatstag, "den Tag im Monat", 1, 28)
        return f"{minute} {stunde} {tag} * *"

    if art == "minuten":
        n = _zahl(abstand, "den Abstand in Minuten", 5, 720)
        return f"*/{n} * * * *"

    if art == "stunden":
        n = _zahl(abstand, "den Abstand in Stunden", 1, 12)
        return f"0 */{n} * * *"

    raise ScheduleError("Bitte auswählen, wie oft die Routine laufen soll.")


def describe(cron: str) -> str:
    """Zeitplan als Satz. Unbekannte Ausdrücke werden nicht beschönigt."""
    felder = (cron or "").split()
    if len(felder) != 5:
        return f"unbekannter Zeitplan ({cron})"

    minute, stunde, tag, monat, wochentag = felder

    if tag == "*" and monat == "*" and wochentag == "*" and minute.isdigit() and stunde.isdigit():
        return f"jeden Tag um {int(stunde):02d}:{int(minute):02d}"

    if tag == "*" and monat == "*" and wochentag == "1-5" and minute.isdigit() and stunde.isdigit():
        return f"werktags um {int(stunde):02d}:{int(minute):02d}"

    if (
        tag == "*"
        and monat == "*"
        and wochentag.isdigit()
        and minute.isdigit()
        and stunde.isdigit()
    ):
        name = dict(WOCHENTAGE).get(wochentag, wochentag)
        return f"jeden {name} um {int(stunde):02d}:{int(minute):02d}"

    if tag.isdigit() and monat == "*" and wochentag == "*" and minute.isdigit() and stunde.isdigit():
        return f"am {int(tag)}. jedes Monats um {int(stunde):02d}:{int(minute):02d}"

    if minute.startswith("*/") and stunde == "*" and tag == "*" and monat == "*" and wochentag == "*":
        return f"alle {minute[2:]} Minuten"

    if minute == "0" and stunde.startswith("*/") and tag == "*" and monat == "*" and wochentag == "*":
        return f"alle {stunde[2:]} Stunden"

    # Wiederholung innerhalb eines Zeitfensters, wie sie die mitgelieferten Routinen nutzen.
    fenster = re.fullmatch(r"(\d{1,2})-(\d{1,2})", stunde)
    if minute.startswith("*/") and fenster and tag == "*" and monat == "*":
        von, bis = int(fenster.group(1)), int(fenster.group(2))
        if wochentag in ("*", "1-5"):
            zusatz = ", werktags" if wochentag == "1-5" else ""
            return f"alle {minute[2:]} Minuten zwischen {von} und {bis} Uhr{zusatz}"
        if wochentag.isdigit():
            name = dict(WOCHENTAGE).get(wochentag, wochentag)
            return f"alle {minute[2:]} Minuten zwischen {von} und {bis} Uhr, jeden {name}"

    return f"unbekannter Zeitplan ({cron})"


@dataclass(frozen=True, slots=True)
class Choice:
    """Was der Nutzer gewählt hat, in Feldern der Seite."""

    art: str = "werktags"
    uhrzeit: str = "08:00"
    wochentag: str = "1"
    monatstag: str = "1"
    abstand: str = "30"

    def cron(self) -> str:
        return cron_from_choice(
            self.art,
            uhrzeit=self.uhrzeit,
            wochentag=self.wochentag,
            monatstag=self.monatstag,
            abstand=self.abstand,
        )
