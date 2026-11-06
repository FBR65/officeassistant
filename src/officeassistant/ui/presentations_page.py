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

from officeassistant.documents import store as dokumente
from officeassistant.presentations import builder, outline, proof, rules, store
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


def _auswahl(dokumente: list, bilder: list) -> tuple[str, str]:
    """Zwei Auswahllisten: Textgrundlage und Bilder."""
    if not dokumente:
        grundlage = (
            "<p style='margin:0;color:#555'>Noch kein Dokument hochgeladen. Laden Sie es unter "
            "<a href=\"/dokumente\">Dokumente</a> hoch; danach steht es hier zur Auswahl.</p>"
        )
    else:
        grundlage = "".join(
            f'<label style="display:block;margin:0.2rem 0">'
            f'<input type="checkbox" name="grundlage" value="{d.id}"> '
            f'Nr. {d.id}: {d.name} ({d.seitenzahl} Seiten)</label>'
            for d in dokumente
        )

    if not bilder:
        bildliste = (
            "<p style='margin:0;color:#555'>Kein Bild hochgeladen. PNG oder JPG unter "
            "<a href=\"/dokumente\">Dokumente</a> hochladen; danach erscheint es hier.</p>"
        )
    else:
        bildliste = "".join(
            f'<label style="display:block;margin:0.2rem 0">'
            f'<input type="checkbox" name="bild" value="{d.id}"> '
            f'Nr. {d.id}: {d.name}</label>'
            for d in bilder
        )
    return grundlage, bildliste


def _formular(dokumente: list | None = None, bilder: list | None = None) -> str:
    grundlage, bildliste = _auswahl(dokumente or [], bilder or [])
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

      <fieldset style="border:1px solid #ddd;padding:0.8rem;border-radius:4px">
        <legend>Grundlage: welche Dokumente?</legend>
        <p style="margin:0 0 0.5rem 0;color:#555;font-size:0.9em">
          Jede gewählte Datei wird als Quelle genannt und ihre Aussagen werden gegen den
          Text geprüft. Ohne Auswahl entsteht die Präsentation nur aus Ihrer Gliederung.
        </p>
        {grundlage}
      </fieldset>

      <fieldset style="border:1px solid #ddd;padding:0.8rem;border-radius:4px">
        <legend>Bilder auf eigenen Folien</legend>
        <p style="margin:0 0 0.5rem 0;color:#555;font-size:0.9em">
          Jedes gewählte Bild bekommt eine eigene Folie mit dem Dateinamen als Beschriftung.
        </p>
        {bildliste}
      </fieldset>

      <kol-input-text _label="Eigene Quellenangabe (freiwillig)" data-name="quelle"
                      _placeholder="Zum Beispiel: Monatsbericht der Abteilung, Stand 31.10.2026">
      </kol-input-text>
      <p style="margin:0;color:#555;font-size:0.9em">
        Diese Zeile steht zusätzlich auf der Quellenfolie. Die Dokumente aus der Auswahl oben
        werden automatisch mit Name, Seiten und Datum genannt — hier ist nichts einzutragen.
      </p>
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
        hochgeladen = dokumente.liste(conn, user.subject)
    finally:
        conn.close()

    ist_bild = lambda eintrag: eintrag.pfad.lower().endswith((".png", ".jpg", ".jpeg"))
    texte = [eintrag for eintrag in hochgeladen if not ist_bild(eintrag)]
    bilder = [eintrag for eintrag in hochgeladen if ist_bild(eintrag)]

    meldung = request.query_params.get("meldung", "")
    with layout.content():
        layout.app_frame("Präsentationen", user.name or user.email)
        layout.nav("/praesentationen")
        if meldung:
            layout.banner(meldung)
        layout.card("Vorhandene Präsentationen", _tabelle(eintraege))
        layout.card("Neue Präsentation aus einer Gliederung", _formular(texte, bilder))
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
    grundlagen = [int(k) for k in formular.getlist("grundlage") if str(k).isdigit()]
    bilder = [int(k) for k in formular.getlist("bild") if str(k).isdigit()]
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

    # Gewählte Bilder bekommen je eine Folie mit dem Dateinamen als Beschriftung.
    if bilder:
        conn_bild = _verbindung()
        try:
            for kennung in bilder:
                try:
                    eintrag = dokumente.hole(conn_bild, user.subject, kennung)
                except dokumente.DokumentFehler as fehler:
                    return RedirectResponse(
                        "/praesentationen?meldung=" + quote(str(fehler)), status_code=303
                    )
                beschreibung["folien"].append(
                    {
                        "titel": f"Bild: {eintrag.name}",
                        "stichpunkte": [],
                        "notiz": f"Auf das Bild {eintrag.name} eingehen, 30 Sekunden.",
                        "bilder": [{"dokument": kennung, "beschriftung": eintrag.name}],
                    }
                )
        finally:
            conn_bild.close()

    # Gewählte Dokumente: Quelle nennen und jede Folie gegen ihren Text prüfen.
    angabe = ""
    texte: list[str] = []
    if grundlagen:
        conn_quelle = _verbindung()
        try:
            angaben = []
            for kennung in grundlagen:
                try:
                    eintrag = dokumente.hole(conn_quelle, user.subject, kennung)
                except dokumente.DokumentFehler as fehler:
                    return RedirectResponse(
                        "/praesentationen?meldung=" + quote(str(fehler)), status_code=303
                    )
                seiten = dokumente.seiten(conn_quelle, eintrag.id)
                texte.append("\n\n".join(seite.text for seite in seiten))
                gelesen = ", ".join(str(seite.nummer) for seite in seiten if seite.text)
                angaben.append(
                    f"{eintrag.name} (Seiten {gelesen}, Stand {eintrag.angelegt.astimezone():%d.%m.%Y})"
                )
        finally:
            conn_quelle.close()
        angabe = ("Dokumente: " if len(angaben) > 1 else "Dokument: ") + "; ".join(angaben)
        beschreibung["quelle"] = (
            f"{beschreibung.get('quelle', '')} · {angabe}"
            if beschreibung.get("quelle")
            else angabe
        )

    try:
        deck = rules.deck_aus_dict(beschreibung)
        if bilder:
            conn_pfad = _verbindung()
            try:
                for folie in deck.folien:
                    for bild in folie.bilder:
                        if bild.get("pfad"):
                            continue
                        try:
                            bild["pfad"] = str(
                                dokumente.als_bild(conn_pfad, user.subject, int(bild["dokument"]))
                            )
                        except (dokumente.DokumentFehler, KeyError, ValueError) as fehler:
                            return RedirectResponse(
                                "/praesentationen?meldung=" + quote(str(fehler)), status_code=303
                            )
            finally:
                conn_pfad.close()

        if texte:
            befunde = proof.pruefe(deck, "\n\n".join(texte))
            if befunde:
                return RedirectResponse(
                    "/praesentationen?meldung="
                    + quote(
                        "Nicht in den Dokumenten belegt: "
                        + "; ".join(str(befund) for befund in befunde[:6])
                    ),
                    status_code=303,
                )

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
