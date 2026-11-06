"""Belegprüfung: Steht das, was auf der Folie steht, auch im gelesenen Dokument?

Das Modell formuliert flüssig und ergänzt dabei gern aus seinem Vorwissen — im Test
tauchte „Amazon Comprehend" auf, obwohl der Artikel nur Textract und Bedrock nennt.

Geprüft werden die belastbaren Teile einer Aussage: Eigennamen, Abkürzungen und Zahlen.
Fließtext und Titel werden nicht geprüft, weil sie umformulieren dürfen. Findet sich ein
Begriff nicht im Quelltext, entsteht **keine** Datei; die Meldung nennt Folie und Begriff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from officeassistant.presentations.rules import Deck

# Wörter, die in Titeln und Folientexten üblich sind und kein Beleg brauchen.
ALLGEMEIN = frozenset(
    {
        "ausgangslage",
        "ablauf",
        "fazit",
        "ergebnis",
        "ergebnisse",
        "zusammenfassung",
        "hintergrund",
        "kennzahlen",
        "dienste",
        "dienst",
        "anfragen",
        "adresse",
        "adressen",
        "informationen",
        "verarbeitung",
        "nächste",
        "naechste",
        "schritte",
        "quellen",
        "übersicht",
        "uebersicht",
        "vorteile",
        "nachteile",
        "grenzen",
        "beispiel",
        "beispiele",
        "aufgabe",
        "aufgaben",
        "lösung",
        "loesung",
        "problem",
        "ziele",
        "stand",
        "ausblick",
        "frage",
        "fragen",
        "antwort",
        "antworten",
        "details",
        "vergleich",
        "einleitung",
        "titel",
        "folie",
        "seite",
        "kapitel",
        "teil",
        "schritt",
        "phase",
        "prozess",
        "system",
        "daten",
        "kosten",
        "zeitplan",
        "team",
        "nutzen",
        "risiko",
        "risiken",
        "technik",
        "architektur",
        "vorbereitung",
        "umsetzung",
    }
)

_ZAHL = re.compile(r"\d{1,2}:\d{2}|\d+(?:[.,]\d+)?\s*%?")
_WORT = re.compile(r"[A-Za-zÄÖÜäöüß0-9][A-Za-zÄÖÜäöüß0-9._+-]*")


@dataclass(frozen=True, slots=True)
class Befund:
    folie: int
    begriff: str

    def __str__(self) -> str:
        return f"Folie {self.folie}: „{self.begriff}“"


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _kandidaten(text: str) -> list[str]:
    """Belastbare Begriffe aus einer Zeile ziehen.

    Geprüft werden Zahlen, Abkürzungen in Großbuchstaben, Wörter mit Großbuchstaben im
    Inneren und Wortpaare aus zwei großgeschriebenen Wörtern („Amazon Comprehend").
    Einzelne großgeschriebene Wörter werden nicht geprüft: im Deutschen ist jedes Substantiv
    groß, das gäbe zu viele Fehlalarme.
    """
    gefunden: list[str] = [treffer.group(0).strip() for treffer in _ZAHL.finditer(text)]

    worte = [(t.group(0), t.start(), t.end()) for t in _WORT.finditer(text)]
    for wort, _start, _ende in worte:
        if len(wort) < 2:
            continue
        if "-" in wort:
            # Zusammensetzungen wie „AWS-Dienste" prüfen ihre Teile, nicht das Ganze.
            gefunden.extend(
                teil
                for teil in wort.split("-")
                if len(teil) >= 2 and teil.isupper()
            )
            continue
        if wort.isupper():  # AWS, S3, PII
            gefunden.append(wort)
        elif any(zeichen.isupper() for zeichen in wort[1:]):  # DynamoDB, Claude2
            gefunden.append(wort)

    # Wortpaare: zwei aufeinanderfolgende großgeschriebene Wörter
    for erster, zweiter in zip(worte, worte[1:]):
        wort_a, _, ende_a = erster
        wort_b, start_b, _ = zweiter
        if text[ende_a : start_b].strip():
            continue  # dazwischen steht ein Satzzeichen
        if not (wort_a[0].isupper() and wort_b[0].isupper()):
            continue
        if wort_a.lower() in ALLGEMEIN and wort_b.lower() in ALLGEMEIN:
            continue
        gefunden.append(f"{wort_a} {wort_b}")

    return gefunden


def _aussagen(folie) -> list[str]:
    """Alles, was auf einer Folie behauptet wird: Stichpunkte, Tabellen, Diagrammnamen."""
    zeilen = [str(punkt) for punkt in folie.stichpunkte]
    if folie.tabelle:
        zeilen.extend(str(z) for z in (folie.tabelle.get("kopf") or []))
        for reihe in folie.tabelle.get("zeilen") or []:
            zeilen.extend(str(wert) for wert in reihe)
    if folie.diagramm:
        zeilen.extend(str(name) for name in (folie.diagramm.get("reihen") or {}))
    return zeilen


def pruefe(deck: Deck, quelle: str) -> list[Befund]:
    """Gibt die Begriffe zurück, die im Quelltext nicht vorkommen."""
    if not quelle.strip():
        return []

    text = _normal(quelle)
    befunde: list[Befund] = []
    gesehen: set[str] = set()

    for nummer, folie in enumerate(deck.folien, start=1):
        # Der Folientitel benennt den Aufbau („Ablauf", „System Overview") und darf
        # umformulieren. Geprüft wird, was als Aussage auf der Folie steht.
        zeilen = _aussagen(folie)
        for zeile in zeilen:
            for begriff in _kandidaten(zeile):
                schluessel = begriff.lower()
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                if schluessel in text:
                    continue
                # Steht jedes Wort des Paares einzeln im Text, ist der Satz gedeckt.
                if " " in begriff and all(
                    teil.lower() in text for teil in begriff.split()
                ):
                    continue
                # Schreibweise mit Bindestrich oder Leerzeichen im Quelltext zulassen
                if schluessel.replace("-", " ") in text or schluessel.replace(" ", "") in text:
                    continue
                befunde.append(Befund(folie=nummer, begriff=begriff))
    return befunde
