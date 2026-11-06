"""PowerPoint-Dateien bauen.

Der Bau folgt den Richtlinien aus `rules.py`. Ist eine Vorlage gesetzt, kommen Layout,
Schrift und Farben aus ihrem Master; die Textmenge, die Notizen und die Fußzeile bleiben
Pflicht und werden zusätzlich gesetzt, wenn die Vorlage sie nicht mitbringt.

Diagramme entstehen als echte PowerPoint-Diagramme (Balken, Kreis), keine Bilder von
Diagrammen: der Nutzer kann die Zahlen später ändern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Cm, Pt

from officeassistant.presentations import rules
from officeassistant.presentations.rules import Deck, Folie, RegelVerstoss


class Bautehler(RuntimeError):
    """Die Datei ließ sich nicht erzeugen."""


def _farbe(wert: str) -> RGBColor:
    return RGBColor.from_string(wert.replace("#", "").upper())


def _folie_mit_titel(prs: Presentation) -> Any:
    """Erste Folie mit Titelplatzhalter; ohne passendes Layout eine leere Folie mit Textfeld."""
    for layout in prs.slide_layouts:
        for platzhalter in layout.placeholders:
            if platzhalter.placeholder_format.type == 1:  # TITLE
                return prs.slides.add_slide(layout)
    return prs.slides.add_slide(prs.slide_layouts[6])


def _text(
    folie: Any,
    links: float,
    oben: float,
    breite: float,
    hoehe: float,
    inhalt: str,
    groesse: int,
    fett: bool = False,
    farbe: str = rules.FARBE_TITEL,
    ausrichtung: Any = None,
) -> Any:
    rahmen = folie.shapes.add_textbox(Cm(links), Cm(oben), Cm(breite), Cm(hoehe))
    rahmen.text_frame.word_wrap = True
    absatz = rahmen.text_frame.paragraphs[0]
    if ausrichtung is not None:
        absatz.alignment = ausrichtung
    lauf = absatz.add_run()
    lauf.text = inhalt
    lauf.font.size = Pt(groesse)
    lauf.font.bold = fett
    lauf.font.color.rgb = _farbe(farbe)
    return rahmen


def _fusszeile(folie: Any, text: str, nummer: int) -> None:
    _text(
        folie,
        links=1.2,
        oben=rules.FUSSZEILE_Y_CM,
        breite=24.0,
        hoehe=0.8,
        inhalt=text,
        groesse=rules.SCHRIFT_FUSSZEILE,
        farbe=rules.FARBE_GRAU,
    )
    _text(
        folie,
        links=rules.BREITE_CM - 4.0,
        oben=rules.FUSSZEILE_Y_CM,
        breite=2.8,
        hoehe=0.8,
        inhalt=str(nummer),
        groesse=rules.SCHRIFT_FUSSZEILE,
        farbe=rules.FARBE_GRAU,
        ausrichtung=PP_ALIGN.RIGHT,
    )


def _notiz(folie: Any, text: str) -> None:
    folie.notes_slide.notes_text_frame.text = text


def _titelzeile(folie: Any, titel: str) -> None:
    """Titel in den Platzhalter, sonst als eigener Text. Vorlage gewinnt bei der Schrift."""
    if folie.shapes.title is not None:
        folie.shapes.title.text = titel
        return
    _text(
        folie,
        links=1.2,
        oben=0.9,
        breite=rules.BREITE_CM - 2.4,
        hoehe=1.8,
        inhalt=titel,
        groesse=rules.SCHRIFT_TITEL_MAX,
        fett=True,
    )


def _stichpunkte(folie: Any, punkte: list[Any], oben: float = 3.4) -> None:
    inhalt = rules.stichpunkte_mit_ebene(punkte)
    rahmen = folie.shapes.add_textbox(
        Cm(1.2), Cm(oben), Cm(rules.BREITE_CM - 2.4), Cm(rules.HOEHE_CM - oben - 2.4)
    )
    rahmen.text_frame.word_wrap = True
    for nummer, (ebene, text) in enumerate(inhalt):
        absatz = (
            rahmen.text_frame.paragraphs[0] if nummer == 0 else rahmen.text_frame.add_paragraph()
        )
        absatz.level = ebene
        absatz.space_after = Pt(10)
        lauf = absatz.add_run()
        lauf.text = ("• " if ebene == 0 else "– ") + text
        lauf.font.size = Pt(rules.schrift_je_ebene(ebene))
        lauf.font.color.rgb = _farbe(rules.FARBE_TITEL)


def _tabelle(folie: Any, angaben: dict[str, Any], oben: float = 3.4) -> None:
    kopf = [str(z) for z in (angaben.get("kopf") or [])]
    zeilen = angaben.get("zeilen") or []
    if not kopf or not zeilen:
        raise Bautehler("Eine Tabelle braucht Kopfzeile und mindestens eine Zeile.")

    spalten = len(kopf)
    reihen = len(zeilen) + 1
    breite = rules.BREITE_CM - 2.4
    hoehe = min(1.1 * reihen, rules.HOEHE_CM - oben - 2.4)
    form = folie.shapes.add_table(reihen, spalten, Cm(1.2), Cm(oben), Cm(breite), Cm(hoehe))
    tabelle = form.table

    for spalte, wert in enumerate(kopf):
        zelle = tabelle.cell(0, spalte)
        zelle.text = wert
        zelle.fill.solid()
        zelle.fill.fore_color.rgb = _farbe(rules.FARBE_AKZENT)
        for absatz in zelle.text_frame.paragraphs:
            for lauf in absatz.runs:
                lauf.font.bold = True
                lauf.font.size = Pt(rules.SCHRIFT_TABELLE)
                lauf.font.color.rgb = _farbe("FFFFFF")

    for reihe, werte in enumerate(zeilen, start=1):
        for spalte, wert in enumerate(list(werte)[:spalten]):
            zelle = tabelle.cell(reihe, spalte)
            zelle.text = str(wert)
            for absatz in zelle.text_frame.paragraphs:
                for lauf in absatz.runs:
                    lauf.font.size = Pt(rules.SCHRIFT_TABELLE)
                    lauf.font.color.rgb = _farbe(rules.FARBE_TITEL)
            if reihe % 2 == 0:
                zelle.fill.solid()
                zelle.fill.fore_color.rgb = _farbe("F2F4F7")


def _diagramm(folie: Any, angaben: dict[str, Any], oben: float = 3.4) -> None:
    art = str(angaben.get("art", "balken")).lower()
    kategorien = [str(k) for k in (angaben.get("kategorien") or [])]
    reihen = angaben.get("reihen") or {}
    if not kategorien or not reihen:
        raise Bautehler("Ein Diagramm braucht Kategorien und mindestens eine Reihe.")

    daten = CategoryChartData()
    daten.categories = kategorien
    for name, werte in reihen.items():
        daten.add_series(str(name), [float(w) for w in werte])

    typen = {
        "balken": XL_CHART_TYPE.COLUMN_CLUSTERED,
        "balken_quer": XL_CHART_TYPE.BAR_CLUSTERED,
        "kreis": XL_CHART_TYPE.PIE,
        "linie": XL_CHART_TYPE.LINE_MARKERS,
    }
    if art not in typen:
        raise Bautehler(f"Unbekannte Diagrammart: {art}")

    rahmen = folie.shapes.add_chart(
        typen[art],
        Cm(1.2),
        Cm(oben),
        Cm(rules.BREITE_CM - 2.4),
        Cm(rules.HOEHE_CM - oben - 2.6),
        daten,
    )
    diagramm = rahmen.chart
    # Der Titel steht auf der Folie, nicht im Diagramm.
    diagramm.has_title = False
    diagramm.has_legend = len(reihen) > 1 or art == "kreis"
    if diagramm.has_legend:
        diagramm.legend.position = XL_LEGEND_POSITION.BOTTOM
        diagramm.legend.include_in_layout = False

    if art == "kreis":
        # Ohne Beschriftung sagt ein Kreis nichts: Anteil je Segment anzeigen.
        plot = diagramm.plots[0]
        plot.has_data_labels = True
        beschriftung = plot.data_labels
        beschriftung.show_category_name = True
        beschriftung.show_value = False
        beschriftung.show_percentage = True
        beschriftung.number_format = "0 %"
        beschriftung.number_format_is_linked = False
        for nummer, punkt in enumerate(plot.series[0].points):
            punkt.format.fill.solid()
            punkt.format.fill.fore_color.rgb = _farbe(
                ["1F6FB2", "3FA9F5", "8A8D93", "B23A48", "1B2430"][nummer % 5]
            )


def _bild(folie: Any, angaben: dict[str, Any], oben: float = 3.4, breite: float = 0) -> None:
    pfad = Path(str(angaben.get("pfad", "")))
    if not pfad.is_file():
        raise Bautehler(f"Bild nicht gefunden: {pfad}")
    bild = folie.shapes.add_picture(
        str(pfad), Cm(1.2), Cm(oben), width=Cm(breite or rules.BREITE_CM - 14.0)
    )
    beschriftung = str(angaben.get("beschriftung", "")).strip()
    if beschriftung:
        _text(
            folie,
            links=1.2,
            oben=oben + bild.height / 360000 + 0.2,
            breite=rules.BREITE_CM - 2.4,
            hoehe=1.0,
            inhalt=beschriftung,
            groesse=12,
            farbe=rules.FARBE_GRAU,
        )


def _platzhalter_fuellen(prs: Presentation, deck: Deck, datum: str) -> None:
    """Füllt `{{titel}}`, `{{untertitel}}` und `{{datum}}` in allen Textrahmen der Vorlage."""
    ersatz = {"{{titel}}": deck.titel, "{{untertitel}}": deck.untertitel, "{{datum}}": datum}
    for folie in prs.slides:
        for form in folie.shapes:
            if not getattr(form, "has_text_frame", False):
                continue
            for absatz in form.text_frame.paragraphs:
                for lauf in absatz.runs:
                    for platzhalter, wert in ersatz.items():
                        if platzhalter in lauf.text:
                            lauf.text = lauf.text.replace(platzhalter, wert)


def baue(
    deck: Deck,
    ziel: Path,
    vorlage: Path | None = None,
    datum: str = "",
) -> Path:
    """Erzeugt die Datei und gibt ihren Pfad zurück."""
    fehler = rules.pruefe(deck, vorlage=vorlage is not None)
    if fehler:
        raise RegelVerstoss(" ".join(fehler))

    if vorlage is not None:
        if not Path(vorlage).is_file():
            raise Bautehler(f"Vorlage nicht gefunden: {vorlage}")
        prs = Presentation(str(vorlage))
        _platzhalter_fuellen(prs, deck, datum)
    else:
        prs = Presentation()
        prs.slide_width = Cm(rules.BREITE_CM)
        prs.slide_height = Cm(rules.HOEHE_CM)

    # Titelfolie
    titel_folie = _folie_mit_titel(prs) if vorlage is not None else prs.slides.add_slide(
        prs.slide_layouts[6]
    )
    if vorlage is not None and titel_folie.shapes.title is not None:
        titel_folie.shapes.title.text = deck.titel
    else:
        _text(
            titel_folie,
            links=1.6,
            oben=6.4,
            breite=rules.BREITE_CM - 3.2,
            hoehe=2.4,
            inhalt=deck.titel,
            groesse=rules.SCHRIFT_TITEL_MAX,
            fett=True,
        )
    if deck.untertitel:
        _text(
            titel_folie,
            links=1.6,
            oben=9.5,
            breite=rules.BREITE_CM - 3.2,
            hoehe=1.6,
            inhalt=deck.untertitel,
            groesse=rules.SCHRIFT_TEXT,
            farbe=rules.FARBE_GRAU,
        )
    # Farbiger Strich unter dem Titel als Gestaltungselement
    # Der Strich steht zwischen Titel und Untertitel, nie auf dem Untertitel.
    strich = titel_folie.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Cm(1.6), Cm(9.05), Cm(6.0), Cm(0.18)
    )
    strich.fill.solid()
    strich.fill.fore_color.rgb = _farbe(rules.FARBE_AKZENT)
    strich.line.fill.background()
    _fusszeile(titel_folie, deck.titel, 1)
    _notiz(titel_folie, "Begrüßung, Thema und Ziel der Präsentation nennen. 30 Sekunden.")

    nummer = 2
    for folie_angaben in deck.folien:
        folie = (
            prs.slides.add_slide(prs.slide_layouts[6])
            if vorlage is not None
            else prs.slides.add_slide(prs.slide_layouts[6])
        )
        _titelzeile(folie, folie_angaben.titel)

        hat_tabelle = bool(folie_angaben.tabelle)
        hat_diagramm = bool(folie_angaben.diagramm)
        hat_bilder = bool(folie_angaben.bilder)

        if hat_tabelle:
            _tabelle(folie, folie_angaben.tabelle or {})
        if hat_diagramm:
            _diagramm(folie, folie_angaben.diagramm or {})
        if hat_bilder:
            # Bild links, Stichpunkte rechts; ohne Stichpunkte nutzt das Bild die volle Breite.
            breite = rules.BREITE_CM - 14.0 if folie_angaben.stichpunkte else rules.BREITE_CM - 2.4
            _bild(folie, folie_angaben.bilder[0], breite=breite)
            if folie_angaben.stichpunkte:
                rahmen = folie.shapes.add_textbox(
                    Cm(rules.BREITE_CM - 12.4), Cm(3.4), Cm(11.2), Cm(rules.HOEHE_CM - 6.0)
                )
                rahmen.text_frame.word_wrap = True
                for i, (ebene, text) in enumerate(
                    rules.stichpunkte_mit_ebene(folie_angaben.stichpunkte)
                ):
                    absatz = (
                        rahmen.text_frame.paragraphs[0]
                        if i == 0
                        else rahmen.text_frame.add_paragraph()
                    )
                    absatz.level = ebene
                    lauf = absatz.add_run()
                    lauf.text = ("• " if ebene == 0 else "– ") + text
                    lauf.font.size = Pt(rules.schrift_je_ebene(ebene))
                    lauf.font.color.rgb = _farbe(rules.FARBE_TITEL)
        elif folie_angaben.stichpunkte and not (hat_tabelle or hat_diagramm):
            _stichpunkte(folie, folie_angaben.stichpunkte)

        _fusszeile(folie, deck.titel, nummer)
        _notiz(folie, folie_angaben.notiz)
        nummer += 1

    if deck.quelle:
        quellen = prs.slides.add_slide(prs.slide_layouts[6])
        _titelzeile(quellen, "Quellen")
        _stichpunkte(quellen, [deck.quelle])
        _fusszeile(quellen, deck.titel, nummer)
        _notiz(quellen, "Quellen nennen und auf Nachfragen verweisen. 20 Sekunden.")

    ziel.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(ziel))
    return ziel


def lies(pfad: Path) -> dict[str, Any]:
    """Liest die Datei zurück: Folienzahl, Titel, Notizen, Tabellen, Diagramme."""
    prs = Presentation(str(pfad))
    folien = []
    for folie in prs.slides:
        texte = []
        tabellen = 0
        diagramme = 0
        for form in folie.shapes:
            if getattr(form, "has_text_frame", False):
                inhalt = form.text_frame.text.strip()
                if inhalt:
                    texte.append(inhalt)
            if getattr(form, "has_table", False):
                tabellen += 1
            if getattr(form, "has_chart", False):
                diagramme += 1
        notiz = ""
        if folie.has_notes_slide:
            notiz = folie.notes_slide.notes_text_frame.text.strip()
        folien.append(
            {
                "texte": texte,
                "notiz": notiz,
                "tabellen": tabellen,
                "diagramme": diagramme,
            }
        )
    return {
        "folienzahl": len(prs.slides),
        "breite_cm": round(prs.slide_width / 360000, 2),
        "hoehe_cm": round(prs.slide_height / 360000, 2),
        "folien": folien,
    }
