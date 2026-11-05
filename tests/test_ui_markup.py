"""Formulare der Oberfläche müssen gültiges HTML sein.

Ein deutsches schließendes Anführungszeichen (") innerhalb eines Attributwerts beendet das
Attribut vorzeitig: aus `_label="Tag im Monat (nur bei „Einmal im Monat")"` wurde sichtbar
`Tag im Monat (nur bei „Einmal im Monat`. Dieser Test liest das erzeugte HTML mit einem
Parser und prüft die Attribute, statt dem Auge zu vertrauen.
"""

from __future__ import annotations

from html.parser import HTMLParser

import pytest


class _Sammler(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elemente: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elemente.append((tag, dict(attrs)))


def _parse(html: str) -> _Sammler:
    sammler = _Sammler()
    sammler.feed(html)
    sammler.close()
    return sammler


@pytest.fixture(scope="module")
def editor() -> str:
    from officeassistant.ui.routines_page import _editor

    return _editor()


def test_every_input_carries_its_name_and_label(editor):
    sammler = _parse(editor)
    felder = [attrs for tag, attrs in sammler.elemente if tag in ("kol-input-text", "kol-textarea")]

    assert {attrs.get("data-name") for attrs in felder} == {
        "name",
        "uhrzeit",
        "monatstag",
        "abstand",
        "prompt",
    }
    for attrs in felder:
        assert attrs.get("_label"), f"Feld {attrs.get('data-name')} ohne Beschriftung"
        assert "„" not in (attrs.get("_label") or "")


def test_labels_are_complete_sentences(editor):
    """Abgeschnittene Beschriftungen enden mitten in der Klammer — hier nicht."""
    sammler = _parse(editor)
    for tag, attrs in sammler.elemente:
        wert = attrs.get("_label") or ""
        if not wert:
            continue
        assert wert.count("(") == wert.count(")"), f"Klammer offen in: {wert!r}"
        assert not wert.rstrip().endswith(("bei", "bei:", "…")), f"Beschriftung endet offen: {wert!r}"


def test_the_editor_has_no_quotes_inside_attributes(editor):
    """Anführungszeichen im Attributwert zerstören das Attribut; sie gehören nicht hinein."""
    import re

    for treffer in re.finditer(r'(_label|_placeholder)="([^"]*)"', editor):
        assert '"' not in treffer.group(2)
    # Und der Rest der Seite darf keine halben Attribute hinterlassen.
    assert editor.count('"') % 2 == 0, "ungerade Zahl von Anführungszeichen im HTML"


def test_the_editor_shows_real_defaults(editor):
    """Ein Platzhalter ist kein Wert: Uhrzeit und Abstand müssen vorbelegt sein."""
    sammler = _parse(editor)
    werte = {
        attrs.get("data-name"): attrs.get("_value")
        for tag, attrs in sammler.elemente
        if tag == "kol-input-text"
    }
    assert werte["uhrzeit"] == "08:00"
    assert werte["monatstag"] == "1"
    assert werte["abstand"] == "30"


def test_every_form_field_has_a_name_for_the_bridge():
    """Ohne `data-name` schreibt die JS-Brücke den Wert nicht ins Formular."""
    import pathlib
    import re

    fehlend = []
    for datei in pathlib.Path("src/officeassistant/ui").glob("*.py"):
        text = datei.read_text()
        for treffer in re.finditer(r"<kol-(?:input-text|textarea)([^>]*)>", text, re.S):
            if "data-name" not in treffer.group(1):
                fehlend.append(f"{datei.name}: {' '.join(treffer.group(1).split())[:60]}")
    assert fehlend == [], "Felder ohne data-name: " + "; ".join(fehlend)


def test_the_admin_form_shows_real_role_options():
    from officeassistant.ui import admin_page

    formular = admin_page._formular()

    assert "<option value=\"member\">" in formular
    assert "<option value=\"admin\">" in formular
    assert "{ROLLEN_OPTIONEN}" not in formular


def test_the_admin_list_shows_real_role_options():
    from officeassistant.store.users import AppUser
    from officeassistant.ui import admin_page

    html = admin_page._tabelle(
        [AppUser("u1", "a@example.org", "A", "member", True)]
    )

    assert "<option value=\"admin\">" in html
    assert "kol-select" not in html
