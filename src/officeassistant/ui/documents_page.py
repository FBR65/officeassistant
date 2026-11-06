"""Seite „Dokumente": hochladen, Text je Seite anzeigen, löschen.

Der Text kommt aus dem Textlayer der PDF; hat eine Seite keinen, liest die Texterkennung
sie. Was per Texterkennung gelesen wurde, ist an der Seite gekennzeichnet.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

import httpx

from nicegui import ui
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse, Response

from officeassistant.documents import reader, store
from officeassistant.documents.ocr import OcrClient
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

VERFAHREN = {
    "textlayer": "aus dem Textlayer",
    "ocr": "per Texterkennung gelesen",
    "fehler": "nicht gelesen",
}


def _verbindung():
    return db.connect(SETTINGS.db_url, autocommit=True)


def _ocr() -> OcrClient:
    return OcrClient(
        base_url=SETTINGS.ocr_base_url,
        model=SETTINGS.ocr_model,
        api_key=SETTINGS.ocr_api_key,
        timeout=SETTINGS.ocr_timeout_s,
    )


def _groesse(wert: int) -> str:
    if wert >= 1024 * 1024:
        return f"{wert / 1024 / 1024:.1f} MB"
    return f"{max(1, round(wert / 1024))} KB"


def _liste(eintraege: list[store.Dokument]) -> str:
    if not eintraege:
        return "<p>Noch kein Dokument hochgeladen.</p>"
    bloecke = []
    for eintrag in eintraege:
        ocr_teil = (
            f" · {eintrag.per_ocr} Seite(n) per Texterkennung"
            if eintrag.per_ocr
            else ""
        )
        bloecke.append(
            f"""
            <div style="border-top:1px solid #eee;padding:0.9rem 0">
              <div style="font-size:1.05em"><strong>{eintrag.name}</strong></div>
              <div style="color:#555;margin:0.2rem 0 0.5rem 0">
                {eintrag.angelegt.astimezone():%d.%m.%Y %H:%M} · {eintrag.seitenzahl} Seiten ·
                {eintrag.zeichen} Zeichen{ocr_teil} · {_groesse(eintrag.groesse)}
              </div>
              <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
                <kol-button _label="Anzeigen" _variant="primary"
                            data-href="/dokumente/{eintrag.id}"></kol-button>
                <form method="post" action="/dokumente/{eintrag.id}/praesentation">
                  <kol-button _label="Präsentation daraus erstellen" _variant="primary"></kol-button>
                </form>
                <kol-button _label="Herunterladen" _variant="secondary"
                            data-href="/dokumente/{eintrag.id}/datei"></kol-button>
                <form method="post" action="/dokumente/{eintrag.id}/loeschen">
                  <kol-button _label="Löschen" _variant="secondary"></kol-button>
                </form>
              </div>
            </div>
            """
        )
    return "".join(bloecke)


def _formular() -> str:
    return """
    <form method="post" action="/dokumente/hochladen" enctype="multipart/form-data"
          style="display:flex;flex-direction:column;gap:1rem">
      <label for="datei">Datei (PDF, PNG oder JPG, höchstens 20 MB)</label>
      <input id="datei" name="datei" type="file" accept=".pdf,.png,.jpg,.jpeg"
             style="padding:0.4rem">
      <div><kol-button _label="Hochladen und Text lesen" _variant="primary"></kol-button></div>
      <p style="margin:0;color:#555;font-size:0.9em">
        Hat eine Seite keinen Textlayer, liest die Texterkennung sie mit 200 dpi. Das dauert
        je Seite einige Sekunden; die Seite zeigt danach, was aus welchem Verfahren stammt.
      </p>
    </form>
    """


@ui.page("/dokumente")
async def dokumente(request: Request) -> Response | None:
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
        layout.app_frame("Dokumente", user.name or user.email)
        layout.nav("/dokumente")
        if meldung:
            layout.banner(meldung)
        layout.card(
            "Vorhandene Dokumente",
            "<p style=\"margin:0 0 0.6rem 0;color:#555\">Der Knopf „Präsentation daraus "
            "erstellen“ beauftragt den Assistenten. Die Datei erscheint danach unter "
            "<a href=\"/praesentationen\">Präsentationen</a>; das dauert einige Minuten.</p>"
            + _liste(eintraege),
        )
        layout.card("Dokument hochladen", _formular())
    return None


@ui.page("/dokumente/{kennung}")
async def anzeigen(request: Request) -> Response | None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        try:
            eintrag = store.hole(conn, user.subject, kennung)
        except store.DokumentFehler as fehler:
            return Response(str(fehler), status_code=403)
        seiten = store.seiten(conn, eintrag.id)
    finally:
        conn.close()

    with layout.content():
        layout.app_frame(eintrag.name, user.name or user.email)
        layout.nav("/dokumente")
        layout.card(
            "Angaben",
            f"<p>{eintrag.seitenzahl} Seiten · {eintrag.zeichen} Zeichen · "
            f"{eintrag.per_ocr} Seite(n) per Texterkennung</p>",
        )
        for seite in seiten:
            kennzeichnung = VERFAHREN.get(seite.verfahren, seite.verfahren)
            inhalt = seite.text or f"<p style='color:#555'>{seite.hinweis or 'Kein Text erkannt.'}</p>"
            layout.card(
                f"Seite {seite.nummer} — {kennzeichnung}",
                f'<pre style="white-space:pre-wrap;font-size:0.85em;margin:0">{inhalt}</pre>'
                if seite.text
                else inhalt,
            )
    return None


async def hochladen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    formular = await request.form()
    datei = formular.get("datei")
    if datei is None or not hasattr(datei, "read") or not str(getattr(datei, "filename", "")):
        return RedirectResponse(
            "/dokumente?meldung=" + quote("Es wurde keine Datei gewählt."), status_code=303
        )

    name = str(getattr(datei, "filename", "") or "dokument")
    inhalt = await datei.read()  # type: ignore[union-attr]
    if len(inhalt) > SETTINGS.max_upload_bytes:
        grenze = SETTINGS.max_upload_bytes // (1024 * 1024)
        return RedirectResponse(
            "/dokumente?meldung=" + quote(f"Die Datei ist größer als {grenze} MB."),
            status_code=303,
        )

    ordner = store.ordner(SETTINGS.data_dir, user.subject)
    ordner.mkdir(parents=True, exist_ok=True)
    ordner.chmod(0o700)
    ziel = ordner / store.dateiname(name)
    ziel.write_bytes(inhalt)
    ziel.chmod(0o600)

    try:
        gelesen = reader.lese(
            ziel,
            ocr=_ocr(),
            min_textlayer=SETTINGS.ocr_min_textlayer,
            dpi=SETTINGS.ocr_dpi,
        )
    except reader.LeseFehler as fehler:
        ziel.unlink(missing_ok=True)
        return RedirectResponse("/dokumente?meldung=" + quote(str(fehler)), status_code=303)

    (ziel.with_suffix(".txt")).write_text(gelesen.text, encoding="utf-8")

    conn = _verbindung()
    try:
        eintrag = store.ablegen(conn, user.subject, name, ziel, gelesen)
    finally:
        conn.close()

    meldung = (
        f"{eintrag.name}: {eintrag.seitenzahl} Seiten, {eintrag.zeichen} Zeichen"
        + (f", davon {eintrag.per_ocr} per Texterkennung" if eintrag.per_ocr else "")
    )
    return RedirectResponse("/dokumente?meldung=" + quote(meldung), status_code=303)


async def praesentation(request: Request) -> Response:
    """Beauftragt den Assistenten, aus dem Dokument eine Präsentation zu bauen."""
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        try:
            eintrag = store.hole(conn, user.subject, kennung)
        except store.DokumentFehler as fehler:
            return Response(str(fehler), status_code=403)
    finally:
        conn.close()

    try:
        token = await auth.access_token(request, SETTINGS)
    except auth.NotAuthenticated:
        return RedirectResponse("/login", status_code=303)

    auftrag = (
        f"Erstelle aus dem hochgeladenen Dokument Nummer {eintrag.id} ({eintrag.name}) eine "
        "Präsentation mit sechs bis acht Folien. Lies das Dokument zuerst vollständig. Gib bei "
        f"create_presentation die Nummer {eintrag.id} als quelle_dokument an. Jede Folie braucht "
        "eine Sprechnotiz. Nenne am Ende den Dateinamen."
    )
    asyncio.create_task(_beauftragen(token, user.subject, auftrag))
    return RedirectResponse(
        "/dokumente?meldung="
        + quote(
            "Der Assistent arbeitet. Die Präsentation erscheint in einigen Minuten unter "
            "„Präsentationen“."
        ),
        status_code=303,
    )


async def _beauftragen(token: str, user_id: str, auftrag: str) -> None:
    """Lauf im Hintergrund; die Dauer sprengt sonst die Geduld des Browsers."""
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            await client.post(
                f"{SETTINGS.api_base_url}/agents/{SETTINGS.agent_id}/runs",
                headers={"Authorization": f"Bearer {token}"},
                data={"message": auftrag, "stream": "false", "user_id": user_id},
            )
    except httpx.HTTPError:
        return


async def herunterladen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        eintrag = store.hole(conn, user.subject, kennung)
    except store.DokumentFehler as fehler:
        return Response(str(fehler), status_code=403)
    finally:
        conn.close()

    datei = Path(eintrag.pfad)
    if not datei.is_file():
        return Response("Die Datei fehlt auf dem Server.", status_code=404)
    return FileResponse(str(datei), filename=eintrag.name)


async def loeschen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    kennung = int(request.path_params.get("kennung", "0"))

    conn = _verbindung()
    try:
        store.loeschen(conn, user.subject, kennung)
    except store.DokumentFehler as fehler:
        return Response(str(fehler), status_code=403)
    finally:
        conn.close()
    return RedirectResponse(
        "/dokumente?meldung=" + quote("Dokument gelöscht."), status_code=303
    )


def register(app) -> None:
    app.add_route("/dokumente/hochladen", hochladen, methods=["POST"], name="dokument_hochladen")
    app.add_route(
        "/dokumente/{kennung}/datei", herunterladen, methods=["GET"], name="dokument_datei"
    )
    app.add_route(
        "/dokumente/{kennung}/loeschen", loeschen, methods=["POST"], name="dokument_loeschen"
    )
    app.add_route(
        "/dokumente/{kennung}/praesentation",
        praesentation,
        methods=["POST"],
        name="dokument_praesentation",
    )
