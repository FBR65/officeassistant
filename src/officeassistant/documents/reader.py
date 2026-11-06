"""Dokumente lesen: Textlayer zuerst, sonst Texterkennung.

Der Ablauf je Seite folgt DocPipeline:

1. Text aus dem PDF lesen. Ab 40 Zeichen gilt die Seite als gelesen.
2. Sonst die Seite mit 200 dpi als PNG zeichnen und an die Texterkennung geben.
3. Ist die Texterkennung nicht erreichbar, bleibt die Seite leer und der Grund steht dabei.
   Es wird nichts erfunden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from officeassistant.documents.ocr import OcrClient, OcrFehler

BILDENDUNGEN = {".png", ".jpg", ".jpeg"}


class LeseFehler(RuntimeError):
    """Die Datei lässt sich nicht öffnen."""


@dataclass(slots=True)
class Seite:
    nummer: int
    text: str
    verfahren: str  # textlayer | ocr | fehler
    hinweis: str = ""


@dataclass(slots=True)
class Gelesen:
    seiten: list[Seite] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(seite.text for seite in self.seiten if seite.text)

    @property
    def zeichen(self) -> int:
        return len(self.text)

    @property
    def per_ocr(self) -> int:
        return sum(1 for seite in self.seiten if seite.verfahren == "ocr")


def _seiten_aus_bild(pfad: Path) -> list[bytes]:
    """Ein Bild gilt als eine Seite."""
    try:
        # Ein neues, leeres Dokument: `open` würde die Bilddatei als PDF zu lesen versuchen.
        with pymupdf.open() as doc:
            seite = doc.new_page(width=595, height=842)
            seite.insert_image(seite.rect, filename=str(pfad))
            return [seite.get_pixmap(dpi=200).tobytes("png")]
    except Exception as fehler:  # noqa: BLE001
        raise LeseFehler(f"Das Bild lässt sich nicht lesen: {fehler}") from fehler


def lese(
    pfad: Path,
    ocr: OcrClient | None = None,
    min_textlayer: int = 40,
    dpi: int = 200,
) -> Gelesen:
    """Liest alle Seiten. Bei PDFs Seite für Seite, bei Bildern als eine Seite."""
    if not pfad.is_file():
        raise LeseFehler(f"Datei nicht gefunden: {pfad}")

    if pfad.suffix.lower() in BILDENDUNGEN:
        if ocr is None:
            return Gelesen([Seite(1, "", "fehler", "Für Bilder fehlt die Texterkennung.")])
        try:
            text = ocr.text_aus_bild(_seiten_aus_bild(pfad)[0])
        except OcrFehler as fehler:
            return Gelesen([Seite(1, "", "fehler", str(fehler))])
        return Gelesen([Seite(1, text, "ocr")])

    try:
        doc = pymupdf.open(str(pfad))
    except Exception as fehler:  # noqa: BLE001
        raise LeseFehler(f"Die Datei ist kein gültiges PDF: {fehler}") from fehler

    seiten: list[Seite] = []
    with doc:
        if doc.page_count == 0:
            raise LeseFehler("Die Datei enthält keine Seite.")
        for nummer, seite in enumerate(doc, start=1):
            text = (seite.get_text("text") or "").strip()
            if len(text) >= min_textlayer:
                seiten.append(Seite(nummer, text, "textlayer"))
                continue
            if ocr is None:
                seiten.append(
                    Seite(nummer, "", "fehler", "Kein Textlayer und keine Texterkennung eingerichtet.")
                )
                continue
            try:
                png = seite.get_pixmap(dpi=dpi).tobytes("png")
                seiten.append(Seite(nummer, ocr.text_aus_bild(png), "ocr"))
            except OcrFehler as fehler:
                seiten.append(Seite(nummer, "", "fehler", str(fehler)))
    return Gelesen(seiten)
