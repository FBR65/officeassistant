"""Präsentationsrichtlinien als Prüfung.

Die Werte stehen hier zentral, damit Werkzeug, Oberfläche und Tests dieselbe Wahrheit
benutzen. Die Prüfung läuft **vor** dem Erzeugen: zu viele Stichpunkte, fehlende Notiz oder
zu kleine Schrift führen zu einer Meldung, nicht zu einer stillen Abweichung.

Widersprechen sich Vorlage und Richtlinien, gewinnt die Vorlage bei Schrift und Farbe.
Pflicht bleiben Textmenge, Notizen, Fußzeile mit Foliennummer und der Bildnachweis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BREITE_CM = 33.87
HOEHE_CM = 19.05

FARBE_TITEL = "1F2937"
FARBE_AKZENT = "1F6FB2"
FARBE_WARNUNG = "B23A48"
FARBE_GRAU = "8A8D93"
FARBE_HELL = "F2F2F2"

SCHRIFT_TITEL_MIN = 28
SCHRIFT_TITEL_MAX = 32
SCHRIFT_TEXT = 19
SCHRIFT_EBENE2 = 17
SCHRIFT_FUSSZEILE = 10
SCHRIFT_TABELLE = 12

MAX_STICHPUNKTE = 6
MAX_WOERTER = 60
MAX_EBENEN = 2
FUSSZEILE_Y_CM = 17.9

# Platzhalter, die eine Vorlage füllen darf.
PLATZHALTER = ("{{titel}}", "{{untertitel}}", "{{datum}}")


class RegelVerstoss(ValueError):
    """Die Beschreibung verletzt eine Präsentationsrichtlinie."""


@dataclass(slots=True)
class Folie:
    titel: str
    stichpunkte: list[str] = field(default_factory=list)
    notiz: str = ""
    tabelle: dict[str, Any] | None = None
    diagramm: dict[str, Any] | None = None
    bilder: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class Deck:
    titel: str
    untertitel: str = ""
    folien: list[Folie] = field(default_factory=list)
    quelle: str = ""


def _text(wert: Any) -> str:
    """Nimmt Text an. Ein leeres Objekt zählt als fehlender Text, nicht als Text."""
    if isinstance(wert, str):
        return wert.strip()
    if wert is None or isinstance(wert, (dict, list)):
        return ""
    return str(wert).strip()


def deck_aus_dict(daten: dict[str, Any]) -> Deck:
    """Baut die Beschreibung aus der Eingabe des Modells und prüft die Form."""
    if not isinstance(daten, dict):
        raise RegelVerstoss("Die Beschreibung muss ein Objekt sein.")
    titel = _text(daten.get("titel"))
    if not titel:
        raise RegelVerstoss("Der Titel der Präsentation fehlt.")

    roh_folien = daten.get("folien") or []
    if not isinstance(roh_folien, list) or not roh_folien:
        raise RegelVerstoss("Die Präsentation braucht mindestens eine Folie.")

    folien: list[Folie] = []
    for nummer, roh in enumerate(roh_folien, 1):
        if not isinstance(roh, dict):
            raise RegelVerstoss(f"Folie {nummer}: Die Angaben fehlen.")
        folie_titel = _text(roh.get("titel"))
        if not folie_titel:
            raise RegelVerstoss(f"Folie {nummer}: Der Titel fehlt.")
        rohe_punkte = roh.get("stichpunkte") or []
        punkte = [_text(p) for p in rohe_punkte] if isinstance(rohe_punkte, list) else []
        punkte = [p for p in punkte if p]
        folien.append(
            Folie(
                titel=folie_titel,
                stichpunkte=punkte,
                notiz=_text(roh.get("notiz")),
                tabelle=roh.get("tabelle") or None,
                diagramm=roh.get("diagramm") or None,
                bilder=list(roh.get("bilder") or []),
            )
        )
    return Deck(
        titel=titel,
        untertitel=_text(daten.get("untertitel")),
        folien=folien,
        quelle=_text(daten.get("quelle")),
    )


def pruefe(deck: Deck, vorlage: bool = False) -> list[str]:
    """Prüft die Richtlinien. Gibt die Liste der Verstöße zurück, leer heißt bestanden."""
    fehler: list[str] = []

    for nummer, folie in enumerate(deck.folien, 1):
        punkte = stichpunkte_mit_ebene(folie.stichpunkte)
        if len(punkte) > MAX_STICHPUNKTE:
            fehler.append(
                f"Folie {nummer}: {len(punkte)} Stichpunkte, erlaubt sind "
                f"{MAX_STICHPUNKTE}."
            )
        woerter = sum(len(text.split()) for _, text in punkte) + len(folie.titel.split())
        if woerter > MAX_WOERTER:
            fehler.append(
                f"Folie {nummer}: {woerter} Wörter, erlaubt sind {MAX_WOERTER}. "
                "Ein Gedanke je Folie."
            )
        if not folie.notiz:
            fehler.append(f"Folie {nummer}: Die Notiz fehlt. Auf jeder Folie steht, was zu sagen ist.")
        for _, punkt in punkte:
            if punkt.startswith("  ") or punkt.startswith("- "):
                fehler.append(
                    f"Folie {nummer}: Unterpunkte mit Leerzeichen oder Spiegelstrich sind "
                    "nicht vorgesehen; die Ebene kommt aus der Liste."
                )
                break

    if deck.folien and not deck.quelle and any(f.bilder for f in deck.folien):
        fehler.append("Bilder ohne Quelle: Die letzte Folie muss den Bildnachweis nennen.")

    return fehler


def schrift_je_ebene(ebene: int) -> int:
    return SCHRIFT_TEXT if ebene <= 0 else SCHRIFT_EBENE2


def stichpunkte_mit_ebene(roh: list[Any]) -> list[tuple[int, str]]:
    """Nimmt Zeichenketten oder Objekte mit `text` und `ebene` an."""
    ergebnis: list[tuple[int, str]] = []
    for eintrag in roh:
        if isinstance(eintrag, dict):
            ebene = min(max(int(eintrag.get("ebene", 0)), 0), MAX_EBENEN - 1)
            ergebnis.append((ebene, str(eintrag.get("text", "")).strip()))
        else:
            ergebnis.append((0, str(eintrag).strip()))
    return ergebnis
