"""Dokumente: Textlayer, Texterkennung, Ablage (SPEC 2026-11-06, Dokumente)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pymupdf
import pytest

from officeassistant.documents import ocr, reader, store
from officeassistant.store import db

DB_URL = os.environ.get("OA_TEST_DB_URL", "")


def _pdf_mit_text(pfad: Path, seiten: int = 2) -> Path:
    doc = pymupdf.open()
    for nummer in range(1, seiten + 1):
        seite = doc.new_page(width=595, height=842)
        seite.insert_text((72, 100), f"Seite {nummer}: Bericht der Abteilung Organisation.")
    doc.save(str(pfad))
    return pfad


def _pdf_ohne_text(pfad: Path) -> Path:
    """Eine Seite, die nur ein Bild enthält: kein Textlayer, also Aufgabe für die Erkennung."""
    doc = pymupdf.open()
    seite = doc.new_page(width=595, height=842)
    seite.draw_rect(pymupdf.Rect(50, 50, 400, 300), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    doc.save(str(pfad))
    return pfad


def _client_mit_antwort(text: str) -> ocr.OcrClient:
    def antworten(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": text}}]},
        )

    return ocr.OcrClient(
        base_url="http://test/v1",
        model="paddleocr-vl",
        transport=httpx.MockTransport(antworten),
    )


# --- Lesen ---------------------------------------------------------------


def test_a_page_with_a_text_layer_is_read_without_ocr(tmp_path: Path):
    pfad = _pdf_mit_text(tmp_path / "bericht.pdf", seiten=3)

    gelesen = reader.lese(pfad, ocr=None)

    assert len(gelesen.seiten) == 3
    assert all(seite.verfahren == "textlayer" for seite in gelesen.seiten)
    assert "Bericht der Abteilung" in gelesen.text


def test_a_page_without_text_layer_goes_through_ocr(tmp_path: Path):
    pfad = _pdf_ohne_text(tmp_path / "scan.pdf")

    gelesen = reader.lese(pfad, ocr=_client_mit_antwort("Erkannt: Betrag 120 Euro"))

    assert gelesen.seiten[0].verfahren == "ocr"
    assert gelesen.seiten[0].text == "Erkannt: Betrag 120 Euro"


def test_without_ocr_the_reason_is_kept_and_no_text_is_invented(tmp_path: Path):
    pfad = _pdf_ohne_text(tmp_path / "scan.pdf")

    gelesen = reader.lese(pfad, ocr=None)

    assert gelesen.seiten[0].verfahren == "fehler"
    assert gelesen.seiten[0].text == ""
    assert "Texterkennung" in gelesen.seiten[0].hinweis


def test_a_failing_ocr_does_not_break_the_reading(tmp_path: Path):
    def scheitert(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="kaputt")

    client = ocr.OcrClient(
        base_url="http://test/v1",
        model="paddleocr-vl",
        transport=httpx.MockTransport(scheitert),
    )

    gelesen = reader.lese(_pdf_ohne_text(tmp_path / "scan.pdf"), ocr=client)

    assert gelesen.seiten[0].verfahren == "fehler"
    assert "Status 500" in gelesen.seiten[0].hinweis


def test_an_image_counts_as_one_page(tmp_path: Path):
    bild = tmp_path / "seite.png"
    doc = pymupdf.open()
    seite = doc.new_page(width=200, height=200)
    seite.get_pixmap(dpi=72).save(str(bild))
    doc.close()

    gelesen = reader.lese(bild, ocr=_client_mit_antwort("Text aus dem Bild"))

    assert len(gelesen.seiten) == 1
    assert gelesen.seiten[0].verfahren == "ocr"


def test_a_broken_file_is_reported_plainly(tmp_path: Path):
    kaputt = tmp_path / "kaputt.pdf"
    kaputt.write_bytes(b"kein PDF")

    with pytest.raises(reader.LeseFehler, match="kein gültiges PDF"):
        reader.lese(kaputt, ocr=None)


# --- Texterkennung -------------------------------------------------------


def test_the_ocr_client_sends_the_image_and_reads_the_answer():
    gesehen: dict = {}

    def antworten(request: httpx.Request) -> httpx.Response:
        gesehen["koerper"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hallo"}}]})

    client = ocr.OcrClient(
        base_url="http://test/v1", model="paddleocr-vl", transport=httpx.MockTransport(antworten)
    )

    assert client.text_aus_bild(b"PNGDATEN") == "Hallo"
    assert gesehen["koerper"]["model"] == "paddleocr-vl"
    assert "data:image/png;base64," in json.dumps(gesehen["koerper"])


def test_the_ocr_client_reports_a_refusal():
    client = ocr.OcrClient(
        base_url="http://test/v1",
        model="paddleocr-vl",
        transport=httpx.MockTransport(lambda request: httpx.Response(400, text="Modell fehlt")),
    )

    with pytest.raises(ocr.OcrFehler, match="abgelehnt"):
        client.text_aus_bild(b"x")


# --- Ablage --------------------------------------------------------------


@pytest.fixture()
def ablage(tmp_path):
    if not DB_URL:
        pytest.skip("OA_TEST_DB_URL nicht gesetzt")
    conn = db.connect(DB_URL)
    db.migrate(conn)
    conn.execute("TRUNCATE document_page, document, app_user CASCADE")
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-doc', 'd@example.org', 'D')"
    )
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES ('u-fremd', 'f@example.org', 'F')"
    )
    conn.commit()
    yield conn, tmp_path
    conn.close()


@pytest.mark.integration
def test_a_document_belongs_to_its_user(ablage):
    conn, ordner = ablage
    pfad = _pdf_mit_text(ordner / "bericht.pdf")
    gelesen = reader.lese(pfad, ocr=None)

    eintrag = store.ablegen(conn, "u-doc", "bericht.pdf", pfad, gelesen)

    assert store.hole(conn, "u-doc", eintrag.id).seitenzahl == 2
    assert len(store.seiten(conn, eintrag.id)) == 2
    with pytest.raises(store.DokumentFehler):
        store.hole(conn, "u-fremd", eintrag.id)


@pytest.mark.integration
def test_deleting_a_document_removes_pages_and_file(ablage):
    conn, ordner = ablage
    pfad = _pdf_mit_text(ordner / "bericht.pdf")
    eintrag = store.ablegen(conn, "u-doc", "bericht.pdf", pfad, reader.lese(pfad, ocr=None))

    store.loeschen(conn, "u-doc", eintrag.id)

    assert not pfad.exists()
    assert store.liste(conn, "u-doc") == []
    assert store.seiten(conn, eintrag.id) == []


def test_the_document_page_offers_a_presentation_button():
    from officeassistant.ui import documents_page

    seite = documents_page._liste(
        [
            store.Dokument(
                id=1,
                user_id="u-doc",
                name="bericht.pdf",
                pfad="/tmp/bericht.pdf",
                seitenzahl=2,
                zeichen=120,
                per_ocr=0,
                angelegt=__import__("datetime").datetime.now(__import__("datetime").UTC),
            )
        ]
    )

    assert "/dokumente/1/praesentation" in seite
    assert "Präsentation daraus erstellen" in seite


@pytest.mark.integration
def test_an_uploaded_image_can_be_used_as_a_picture(ablage):
    conn, ordner = ablage
    bild = ordner / "foto.png"
    doc = pymupdf.open()
    seite = doc.new_page(width=200, height=200)
    seite.get_pixmap(dpi=72).save(str(bild))
    doc.close()

    eintrag = store.ablegen(
        conn, "u-doc", "foto.png", bild, reader.lese(bild, ocr=_client_mit_antwort("Bild"))
    )

    assert store.als_bild(conn, "u-doc", eintrag.id) == bild


@pytest.mark.integration
def test_a_pdf_is_not_a_picture(ablage):
    conn, ordner = ablage
    pfad = _pdf_mit_text(ordner / "bericht.pdf")
    eintrag = store.ablegen(conn, "u-doc", "bericht.pdf", pfad, reader.lese(pfad, ocr=None))

    with pytest.raises(store.DokumentFehler, match="kein Bild"):
        store.als_bild(conn, "u-doc", eintrag.id)


@pytest.mark.integration
def test_a_foreign_picture_is_refused(ablage):
    conn, ordner = ablage
    bild = ordner / "foto.png"
    doc = pymupdf.open()
    doc.new_page(width=200, height=200).get_pixmap(dpi=72).save(str(bild))
    doc.close()
    eintrag = store.ablegen(
        conn, "u-doc", "foto.png", bild, reader.lese(bild, ocr=_client_mit_antwort("Bild"))
    )

    with pytest.raises(store.DokumentFehler):
        store.als_bild(conn, "u-fremd", eintrag.id)
