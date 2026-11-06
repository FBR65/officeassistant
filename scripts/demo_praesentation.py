"""Baut eine Beispielpräsentation und wandelt sie zur Sichtprüfung in Bilder.

Aufruf: uv run python scripts/demo_praesentation.py [Zielordner]
"""

from __future__ import annotations

import sys
from pathlib import Path

from officeassistant.presentations import builder, rules, store


def main() -> int:
    ziel_ordner = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo")
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    deck = rules.Deck(
        titel="Lagebericht Oktober",
        untertitel="Abteilung Organisation · 6. November 2026",
        quelle="Zahlen aus dem Monatsbericht der Abteilung, Stand 31.10.2026.",
        folien=[
            rules.Folie(
                titel="Ausgangslage",
                stichpunkte=[
                    "Drei Neueinstellungen im Oktober",
                    "Umzug der Abteilung im November",
                    {"text": "Zwei Stellen bleiben bis Januar offen", "ebene": 1},
                ],
                notiz="Kurz die Ausgangslage nennen und auf den Umzug hinweisen. 60 Sekunden.",
            ),
            rules.Folie(
                titel="Kennzahlen",
                tabelle={
                    "kopf": ["Kennzahl", "Ist", "Ziel"],
                    "zeilen": [
                        ["Bearbeitungszeit", "2,4 Tage", "2,0 Tage"],
                        ["Rückfragen je Vorgang", "18", "10"],
                        ["Kundenzufriedenheit", "4,1 von 5", "4,3 von 5"],
                    ],
                },
                notiz="Die Bearbeitungszeit ist der Engpass; Rückfragen hängen daran. 90 Sekunden.",
            ),
            rules.Folie(
                titel="Entwicklung der Vorgänge",
                diagramm={
                    "art": "balken",
                    "kategorien": ["August", "September", "Oktober"],
                    "reihen": {"Vorgänge": [412, 448, 471], "Rückfragen": [22, 25, 18]},
                },
                notiz="Steigende Vorgangszahl bei sinkenden Rückfragen. 60 Sekunden.",
            ),
            rules.Folie(
                titel="Verteilung der Vorgangsarten",
                diagramm={
                    "art": "kreis",
                    "kategorien": ["Anträge", "Auskünfte", "Beschwerden"],
                    "reihen": {"Anteil": [52, 33, 15]},
                },
                notiz="Anträge sind der größte Block; Beschwerden bleiben niedrig. 45 Sekunden.",
            ),
            rules.Folie(
                titel="Nächste Schritte",
                stichpunkte=[
                    "Freigabe der Stellen bis 12.11.",
                    "Umzugstermin am 21.11. bestätigen",
                    "Neue Kennzahlen ab Dezember messen",
                ],
                notiz="Drei Punkte mit Terminen nennen, dann auf Fragen eingehen. 60 Sekunden.",
            ),
        ],
    )

    fehler = rules.pruefe(deck)
    if fehler:
        print("Richtlinien verletzt:", fehler)
        return 1

    pfad = builder.baue(deck, ziel_ordner / store.dateiname(deck.titel))
    gelesen = builder.lies(pfad)
    print("Datei:", pfad, "| Folien:", gelesen["folienzahl"])
    for nummer, folie in enumerate(gelesen["folien"], 1):
        print(
            f"  Folie {nummer}: Tabellen {folie['tabellen']}, Diagramme {folie['diagramme']}, "
            f"Notiz {len(folie['notiz'])} Zeichen"
        )

    bilder = store.vorschau(pfad, ziel_ordner / "_vorschau")
    print("Vorschaubilder:", len(bilder))
    for bild in bilder:
        print("  ", bild)
    return 0


if __name__ == "__main__":
    sys.exit(main())
