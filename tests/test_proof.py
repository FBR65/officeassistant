"""Belegprüfung: Folien gegen den Text eines hochgeladenen Dokuments prüfen."""

from __future__ import annotations

from officeassistant.presentations import proof, rules

QUELLE = """
Das System nutzt Amazon Textract für die Texterkennung und Amazon Bedrock mit Claude Sonnet
4.6 für die Klassifikation. Die drei Lambda-Funktionen heißen ingest_email_image,
extract_text und classify_and_extract_pii. Der Zeitplan startet werktags um 23:55 Uhr.
Die Konfidenz der Zeile lag bei 93,85 Prozent.
"""


def _deck(stichpunkte: list[str], titel: str = "Ablauf") -> rules.Deck:
    return rules.Deck(
        titel="Bericht",
        folien=[
            rules.Folie(titel=titel, stichpunkte=stichpunkte, notiz="Notiz mit Zeitangabe.")
        ],
    )


def test_a_term_from_the_source_passes():
    deck = _deck(["Amazon Textract liest den Text", "Bedrock klassifiziert mit Claude Sonnet"])

    assert proof.pruefe(deck, QUELLE) == []


def test_an_invented_service_is_caught():
    deck = _deck(["Amazon Comprehend ergänzt die Analyse"])

    befunde = proof.pruefe(deck, QUELLE)

    assert [befund.begriff for befund in befunde] == ["Amazon Comprehend"]
    assert befunde[0].folie == 1


def test_numbers_must_appear_in_the_source():
    deck = _deck(["Die Erkennung startet werktags um 22:15 Uhr", "Konfidenz 93,85 Prozent"])

    begriffe = [befund.begriff for befund in proof.pruefe(deck, QUELLE)]

    assert "22:15" in begriffe
    assert "93,85" not in begriffe


def test_common_slide_words_are_not_checked():
    deck = _deck([], titel="Ausgangslage")
    deck.folien[0].stichpunkte = ["Nächste Schritte", "Fazit", "Ergebnis"]

    assert proof.pruefe(deck, QUELLE) == []


def test_without_a_source_nothing_is_checked():
    deck = _deck(["Amazon Comprehend"])

    assert proof.pruefe(deck, "") == []


def test_the_hint_names_the_slide_and_the_term():
    deck = _deck(["Amazon Comprehend hilft"])

    text = str(proof.pruefe(deck, QUELLE)[0])

    assert text.startswith("Folie 1:")
    assert "Comprehend" in text


def test_a_hyphenated_heading_is_checked_by_its_parts():
    """„AWS-Dienste" wird über den Teil „AWS" geprüft, nicht über den Wortlaut."""
    deck = _deck([], titel="AWS-Dienste")

    assert [befund.begriff for befund in proof.pruefe(deck, QUELLE)] == ["AWS"]


def test_with_the_part_in_the_source_the_heading_passes():
    deck = _deck([], titel="AWS-Dienste")

    assert proof.pruefe(deck, "Der Dienst läuft bei AWS.") == []
