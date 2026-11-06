"""Gliederung aus Freitext lesen (Formular der Seite „Präsentationen").

Format je Folie, Blöcke durch eine Leerzeile getrennt::

    # Ausgangslage
    - Drei Neueinstellungen
    - Umzug im November
    Notiz: Kurz auf die Zahlen eingehen. 60 Sekunden.

Der Titel einer Folie beginnt mit `#`. Stichpunkte beginnen mit `-`. Die Zeile `Notiz:`
füllt die Sprechnotiz. Fehlt sie, meldet der Leser das mit der Foliennummer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class GliederungFehler(ValueError):
    """Der Freitext lässt sich nicht in Folien übersetzen."""


@dataclass(slots=True)
class Rohfolie:
    titel: str
    stichpunkte: list[str] = field(default_factory=list)
    notiz: str = ""


def lese(text: str) -> list[Rohfolie]:
    folien: list[Rohfolie] = []
    aktuelle: Rohfolie | None = None

    for zeile_nummer, zeile in enumerate(text.splitlines(), 1):
        zeile = zeile.rstrip()
        if not zeile.strip():
            aktuelle = None
            continue
        if zeile.lstrip().startswith("#"):
            titel = zeile.lstrip("# ").strip()
            if not titel:
                raise GliederungFehler(f"Zeile {zeile_nummer}: Der Folientitel fehlt.")
            aktuelle = Rohfolie(titel=titel)
            folien.append(aktuelle)
            continue
        if aktuelle is None:
            raise GliederungFehler(
                f"Zeile {zeile_nummer}: Die Zeile steht vor dem ersten Folientitel. "
                'Jede Folie beginnt mit einem Titel in der Form "# Titel".' 
            )
        inhalt = zeile.strip()
        if inhalt.lower().startswith("notiz:"):
            aktuelle.notiz = inhalt.split(":", 1)[1].strip()
        elif inhalt.startswith("-"):
            aktuelle.stichpunkte.append(inhalt.lstrip("- ").strip())
        else:
            aktuelle.stichpunkte.append(inhalt)

    if not folien:
        raise GliederungFehler(
            'Die Gliederung ist leer. Jede Folie beginnt mit einem Titel in der Form "# Titel".'
        )
    return folien


def als_beschreibung(titel: str, untertitel: str, text: str) -> dict:
    """Baut die Eingabe für den Baustein und prüft, dass jede Folie eine Notiz hat."""
    folien = []
    fehlend = []
    for nummer, folie in enumerate(lese(text), 1):
        if not folie.notiz:
            fehlend.append(nummer)
        folien.append(
            {"titel": folie.titel, "stichpunkte": folie.stichpunkte, "notiz": folie.notiz}
        )
    if fehlend:
        zahlen = ", ".join(str(n) for n in fehlend)
        raise GliederungFehler(
            "Auf jeder Folie fehlt die Sprechnotiz. Ergänzen Sie die Zeile "
            f'"Notiz:" bei Folie {zahlen}.' 
        )
    return {"titel": titel, "untertitel": untertitel, "folien": folien}
