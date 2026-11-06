"""Seite „Präsentationen": Liste, Anlegen aus einer Gliederung, Herunterladen, Vorschau.

Die Seite erzeugt die Datei ohne Modellaufruf. Wer den Assistenten bemühen will, stellt den
Auftrag unter „Aufträge"; beide Wege enden in derselben Ablage.
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse, Response

from officeassistant.presentations import builder, outline, rules, store
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

BEISPIEL = """# Ausgangslage
- Drei Neueinstellungen im Oktober
- Umzug der Abteilung im November
Notiz: Kurz die Ausgangslage nennen, 60 Sekunden.

# Kennzahlen
Tabelle: Kennzahl | Ist | Ziel
- Bearbeitungszeit | 2,4 Tage | 2,0 Tage
- Rückfragen | 18 | 10
Notiz: Auf die Bearbeitungszeit eingehen, 90 Sekunden.
"""


def _verbindung():
    return db.connect(SETTINGS.db_url, autocommit=True)


def _groesse(bytes_wert: int) -> str:
    if bytes_wert >= 1024 * 1024:
        return f"{bytes_wert / 1024 / 1024:.1f} MB"
    return f"{max(1, round(bytes_wert / 1024))} KB"


def _tabelle(eintraege: list[store.Praesentation]) -> str:
    if not eintraege:
        return "<p>Noch keine Präsentation erstellt.</p>"

    bloecke = []
    for eintrag in eintraege:
        zeit = eintrag.angelegt.astimezone()
        quelle = f" · Vorlage: {eintrag.vorlage}" if eintrag.vorlage else ""
        bloecke.append(
            f"""
            <div style="border-top:1px solid #eee;padding:0.9rem 0">
              <div style="font-size:1.05em"><strong>{eintrag.titel}</strong></div>
              <div style="color:#555;margin:0.2rem 0 0.5rem 0">
                {zeit:%d.%m.%Y %H:%M} · {eintrag.folienzahl} Folien · {_groesse(eintrag.groesse)}{quelle}
              </div>
              <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
                <kol-button _label="Herunterladen" _variant="primary"
                            data-href="/praesentationen/{eintrag.id}/datei"></kol-button>
                <kol-button _label="Vorschau" _variant="secondary"
                            data-href="/praesentationen/{eintrag.id}/vorschau"></kol-button>
                <form method="post" action="/praesentationen/{eintrag.id}/loeschen">
                  <kol-button _label="Löschen" _variant="secondary"></kol-button>
                </form>
              </div>
            </div>
            """
        )
    return "".join(bloecke)


def _formular() -> str:
    vorlage = SETTINGS.presentation_template
    hinweis = (
        f"Designvorlage: {Path(vorlage).name}"
        if vorlage and Path(vorlage).is_file()
        else "Keine Designvorlage eingerichtet; es gilt die eingebaute Gestaltung."
    )
    return f"""
    <form method="post" action="/praesentationen/erzeugen"
          style="display:flex;flex-direction:column;gap:1rem">
      <p style="margin:0;color:#555">{hinweis}</p>
      <kol-input-text _label="Titel der Präsentation" data-name="titel" _required="true"></kol-input-text>
      <kol-input-text _label="Untertitel" data-name="untertitel"></kol-input-text>
      <kol-textarea _label="Gliederung" data-name="gliederung" _rows="12">{BEISPIEL}</kol-textarea>
      <kol-input-text _label="Quellen und Bildnachweis" data-name="quelle"></kol-input-text>
      <div><kol-button _label="Präsentation erstellen" _variant="primary"></kol-button></div>
      <p style="margin:0;color:#555;font-size:0.9em">
        Jede Folie beginnt mit „# Titel". Stichpunkte beginnen mit „-". Die Zeile „Notiz:"
        enthält, was zu sagen ist; sie ist auf jeder Folie Pflicht. Eine Zeile
        „Tabelle: A | B | C" leitet eine Tabelle ein, die folgenden Zeilen sind ihre Werte.
      </p>
    </form>
    """


@ui.page("/praesentationen")
async def praesentationen(request: Request) -> Response | None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    conn = _verbindung()
    try:
        eintraege = store.liste(conn, user.subject)
    finally:
        conn.close()

    meldung = request.query_params.get("meldung", "")
    with layout.content():
        layout.app_frame("Präsentationen", user.name or user.email)
        layout.nav("/praesentationen")
        if meldung:
            layout.banner(meldung)
        layout.card("Vorhandene Präsentationen", _tabelle(eintraege))
        layout.card("Neue Präsentation aus einer Gliederung", _formular())
    return None


def _tabelle_aus_zeilen(folie: dict, zeilen_basis: list[str]) -> None:
    """Zweite Zeile einer Folie kann eine Tabelle einleiten: `Tabelle: A | B`."""
    if not zeilen_basis:
        return
    kopf = [teil.strip() for teil in zeilen_basis[0].split("|")]
    werte = []
    for zeile in zeilen_basis[1:]:
        werte.append([teil.strip() for teil in zeile.split("|")])
    if kopf and werte:
        folie["tabelle"] = {"kopf": kopf, "zeilen": werte}


async def erzeugen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    formular = await request.form()
    titel = str(formular.get("titel", "")).strip()
    untertitel = str(formular.get("untertitel", "")).strip()
    gliederung = str(formular.get("gliederung", ""))
    quelle = str(formular.get("quelle", "")).strip()

    if not titel:
        return RedirectResponse(
            "/praesentationen?meldung=" + quote("Der Titel fehlt."), status_code=303
        )

    try:
        beschreibung = outline.als_beschreibung(titel, untertitel, gliederung)
    except outline.GliederungFehler as fehler:
        return RedirectResponse("/praesentationen?meldung=" + quote(str(fehler)), status_code=303)

    # Tabellenzeilen aus der Gliederung herausnehmen
    for folie in beschreibung["folien"]:
        tabelle_zeilen = [z for z in folie["stichpunkte"] if "|" in z]
        uebrig = [z for z in folie["stichpunkte"] if "|" not in z]
        folie["stichpunkte"] = uebrig
        _tabelle_aus_zeilen(folie, tabelle_zeilen)

    try:
        deck = rules.deck_aus_dict(beschreibung)
        vorlage = Path(SETTINGS.presentation_template) if SETTINGS.presentation_template else None
        ziel = store.ordner(SETTINGS.data_dir, user.subject) / store.dateiname(titel)
        builder.baue(deck, ziel, vorlage=vorlage if vorlage and vorlage.is_file() else None)
    except (rules.RegelVerstoss, builder.Bautehler) as fehler:
        return RedirectResponse("/praesentationen?meldung=" + quote(str(fehler)), status_code=303)

    gelesen = builder.lies(ziel)
    conn = _verbindung()
    try:
        eintrag = store.anlegen(
            conn, SETTINGS.data_dir, user.subject, deck.titel, ziel, int(gelesen["folienzahl"]),
            vorlage.name if vorlage and vorlage.is_file() else "",
        )
    finally:
        conn.close()

    return RedirectResponse(
        "/praesentationen?meldung=" + quote(f"Erstellt: {eintrag.titel} ({eintrag.folienzahl} Folien)"),
        status_code=303,
    )


async def herunterladen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        eintrag = store.hole(conn, user.subject, kennung)
    except store.AblageFehler as fehler:
        return Response(str(fehler), status_code=403)
    finally:
        conn.close()

    datei = Path(eintrag.pfad)
    if not datei.is_file():
        return Response("Die Datei fehlt auf dem Server.", status_code=404)
    return FileResponse(
        str(datei),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=eintrag.dateiname,
    )


async def loeschen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        store.loeschen(conn, user.subject, kennung)
    except store.AblageFehler as fehler:
        return Response(str(fehler), status_code=403)
    finally:
        conn.close()
    return RedirectResponse(
        "/praesentationen?meldung=" + quote("Präsentation gelöscht."), status_code=303
    )


@ui.page("/praesentationen/{kennung}/vorschau")
async def vorschau(request: Request) -> Response | None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        eintrag = store.hole(conn, user.subject, kennung)
    except store.AblageFehler as fehler:
        return Response(str(fehler), status_code=403)
    finally:
        conn.close()

    ordner = Path(SETTINGS.data_dir) / "praesentationen" / store._sauber(user.subject, 80) / "_vorschau"
    for alt in ordner.glob("folie*.png"):
        alt.unlink(missing_ok=True)
    bilder = store.vorschau(Path(eintrag.pfad), ordner)

    with layout.content():
        layout.app_frame("Vorschau", user.name or user.email)
        layout.nav("/praesentationen")
        if not bilder:
            layout.card(
                "Vorschau nicht möglich",
                "<p>LibreOffice oder die Bildumwandlung fehlt auf dem Server.</p>",
            )
        for nummer, bild in enumerate(bilder, 1):
            ui.image(str(bild)).classes("w-full")
            ui.html(f'<p style="color:#555;margin:0 0 1rem 0">Folie {nummer}</p>', sanitize=False)
    return None


def register(app) -> None:
    app.add_route(
        "/praesentationen/erzeugen", erzeugen, methods=["POST"], name="praesentation_erzeugen"
    )
    app.add_route(
        "/praesentationen/{kennung}/datei", herunterladen, methods=["GET"], name="praesentation_datei"
    )
    app.add_route(
        "/praesentationen/{kennung}/loeschen",
        loeschen,
        methods=["POST"],
        name="praesentation_loeschen",
    )
