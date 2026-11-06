"""Präsentationen: Richtlinien, Bau, Ablage, Gliederung (SPEC 2026-11-06)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from officeassistant.presentations import builder, outline, rules, store
from officeassistant.store import db

DB_URL = os.environ.get("OA_TEST_DB_URL", "")
integration = [
    pytest.mark.integration,
    pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt"),
]


def _deck(**abweichungen) -> rules.Deck:
    folie = rules.Folie(
        titel="Ausgangslage",
        stichpunkte=["Drei Neueinstellungen", "Umzug im November"],
        notiz="Kurz die Ausgangslage nennen. 60 Sekunden.",
    )
    angaben = {"titel": "Lagebericht", "untertitel": "Abteilung", "folien": [folie]}
    angaben.update(abweichungen)
    return rules.Deck(**angaben)


# --- Richtlinien ---------------------------------------------------------


def test_a_clean_deck_passes_the_rules():
    deck = _deck()
    assert rules.pruefe(deck) == []


def test_seven_bullets_are_rejected():
    folie = rules.Folie(
        titel="Zu viel",
        stichpunkte=[f"Punkt {nummer}" for nummer in range(1, 8)],
        notiz="Notiz vorhanden.",
    )
    fehler = rules.pruefe(_deck(folien=[folie]))

    assert any("7 Stichpunkte" in text for text in fehler)


def test_a_missing_note_is_rejected():
    folie = rules.Folie(titel="Ohne Notiz", stichpunkte=["Eins"], notiz="")
    fehler = rules.pruefe(_deck(folien=[folie]))

    assert any("Notiz fehlt" in text for text in fehler)


def test_too_much_text_is_rejected():
    folie = rules.Folie(
        titel="Viel Text",
        stichpunkte=[" ".join(["Wort"] * 20) for _ in range(4)],
        notiz="Notiz vorhanden.",
    )
    fehler = rules.pruefe(_deck(folien=[folie]))

    assert any("Wörter" in text for text in fehler)


def test_images_need_a_source():
    folie = rules.Folie(
        titel="Mit Bild",
        stichpunkte=["Ein Punkt"],
        notiz="Notiz vorhanden.",
        bilder=[{"pfad": "/tmp/bild.png"}],
    )
    fehler = rules.pruefe(_deck(folien=[folie]))

    assert any("Bildnachweis" in text for text in fehler)


def test_the_description_needs_a_title_and_a_slide():
    with pytest.raises(rules.RegelVerstoss):
        rules.deck_aus_dict({"folien": [{"titel": "A"}]})
    with pytest.raises(rules.RegelVerstoss):
        rules.deck_aus_dict({"titel": "T", "folien": []})


# --- Bau -----------------------------------------------------------------


def test_the_built_file_keeps_the_rules(tmp_path: Path):
    ziel = tmp_path / "deck.pptx"
    builder.baue(_deck(), ziel)

    gelesen = builder.lies(ziel)

    assert gelesen["folienzahl"] == 2  # Titelfolie und eine Inhaltsfolie
    assert round(gelesen["breite_cm"]) == 34
    assert gelesen["folien"][0]["notiz"] != ""
    assert any("Lagebericht" in text for text in gelesen["folien"][0]["texte"])


def test_tables_and_charts_reach_the_file(tmp_path: Path):
    folie = rules.Folie(
        titel="Zahlen",
        notiz="Zahlen erklären. 90 Sekunden.",
        tabelle={"kopf": ["Kennzahl", "Ist"], "zeilen": [["Zeit", "2,4 Tage"]]},
        diagramm={
            "art": "balken",
            "kategorien": ["Jan", "Feb"],
            "reihen": {"Anrufe": [3, 5]},
        },
    )
    ziel = tmp_path / "zahlen.pptx"
    builder.baue(_deck(folien=[folie]), ziel)

    gelesen = builder.lies(ziel)

    assert gelesen["folien"][1]["tabellen"] == 1
    assert gelesen["folien"][1]["diagramme"] == 1


def test_a_broken_rule_stops_the_build(tmp_path: Path):
    folie = rules.Folie(titel="Ohne Notiz", stichpunkte=["Eins"], notiz="")
    ziel = tmp_path / "verboten.pptx"

    with pytest.raises(rules.RegelVerstoss):
        builder.baue(_deck(folien=[folie]), ziel)
    assert not ziel.exists()


def test_a_template_supplies_the_layout(tmp_path: Path):
    vorlage = tmp_path / "vorlage.pptx"
    builder.baue(_deck(titel="Vorlage", folien=[]), vorlage)

    ziel = tmp_path / "aus-vorlage.pptx"
    builder.baue(_deck(), ziel, vorlage=vorlage)

    gelesen = builder.lies(ziel)
    assert gelesen["folienzahl"] >= 2


def test_the_preview_needs_libreoffice(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store.shutil, "which", lambda name: None)

    assert store.vorschau(tmp_path / "egal.pptx", tmp_path / "out") == []


# --- Gliederung ----------------------------------------------------------


def test_the_outline_reader_understands_headings_bullets_and_notes():
    text = "# Ausgangslage\n- Drei Neueinstellungen\n- Umzug\nNotiz: Kurz nennen."

    folien = outline.lese(text)

    assert folien[0].titel == "Ausgangslage"
    assert folien[0].stichpunkte == ["Drei Neueinstellungen", "Umzug"]
    assert folien[0].notiz == "Kurz nennen."


def test_the_outline_reader_demands_a_note():
    with pytest.raises(outline.GliederungFehler, match="Sprechnotiz"):
        outline.als_beschreibung("T", "", "# Eins\n- Punkt")


def test_the_outline_reader_refuses_text_before_the_first_heading():
    with pytest.raises(outline.GliederungFehler, match="vor dem ersten Folientitel"):
        outline.lese("- Punkt ohne Titel")


# --- Ablage --------------------------------------------------------------


@pytest.fixture()
def ablage(tmp_path):
    if not DB_URL:
        pytest.skip("OA_TEST_DB_URL nicht gesetzt")
    conn = db.connect(DB_URL)
    db.migrate(conn)
    conn.execute("TRUNCATE presentation, app_user CASCADE")
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-praes', 'p@example.org', 'P')"
    )
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-fremd', 'f@example.org', 'F')"
    )
    conn.commit()
    yield conn, tmp_path
    conn.close()


@pytest.mark.integration
def test_a_presentation_belongs_to_its_user(ablage):
    conn, ordner = ablage
    pfad = ordner / "deck.pptx"
    builder.baue(_deck(), pfad)

    eintrag = store.anlegen(conn, str(ordner), "u-praes", "Lagebericht", pfad, 2)

    assert store.hole(conn, "u-praes", eintrag.id).titel == "Lagebericht"
    with pytest.raises(store.AblageFehler):
        store.hole(conn, "u-fremd", eintrag.id)
    with pytest.raises(store.AblageFehler):
        store.loeschen(conn, "u-fremd", eintrag.id)


@pytest.mark.integration
def test_deleting_removes_the_file(ablage):
    conn, ordner = ablage
    pfad = ordner / "deck.pptx"
    builder.baue(_deck(), pfad)
    eintrag = store.anlegen(conn, str(ordner), "u-praes", "Lagebericht", pfad, 2)

    store.loeschen(conn, "u-praes", eintrag.id)

    assert not pfad.exists()
    assert store.liste(conn, "u-praes") == []
