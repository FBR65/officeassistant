"""Seite „Post": Postfach lesen und Antworten entwerfen.

Gelesen wird über den Anbieter des angemeldeten Nutzers (IMAP, Testpostfach). Gesendet wird
hier nicht: Entwürfe landen im Postfach, das Senden bleibt bei der Freigabe.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from officeassistant.agents.session import NoMailbox, resolve_session
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()
MAX_ANZEIGE = 25
CACHE_SEKUNDEN = 30

# Kopfzeilen je Nutzer kurz halten: ein Gmail-Abruf dauert Sekunden, und nach dem Senden
# wird die Seite neu aufgebaut.
_CACHE: dict[str, tuple[float, list]] = {}


def _seite(user_id: str, kennung: str) -> tuple[str, str, str]:
    """Liste, Nachricht und Antwortformular in einem Durchgang (eine Verbindung).

    Netzaufrufe dürfen den Hauptfaden nicht blockieren; der Aufrufer schiebt diese
    Funktion in einen Arbeitsfaden.
    """
    liste = _liste(user_id, kennung)
    if not kennung:
        return liste, "", ""

    try:
        session = _postfach(user_id)
        nachricht = session.provider.get_message(kennung)
    except Exception as fehler:  # noqa: BLE001 - Anzeige statt Absturz
        return liste, f"<p>Die Nachricht lässt sich nicht lesen: {fehler}</p>", ""

    text = nachricht.body_text.replace("&", "&amp;").replace("<", "&lt;")
    nachricht_html = f"""
    <p style="margin:0 0 0.5rem 0">
      <strong>{nachricht.header.subject or '(ohne Betreff)'}</strong><br>
      <span style="color:#555">von {nachricht.header.sender}
      am {nachricht.header.received_at.astimezone():%d.%m.%Y %H:%M}</span>
    </p>
    <pre style="white-space:pre-wrap;font-family:inherit;margin:0">{text[:4000]}</pre>
    """

    absender = nachricht.header.sender
    if "<" in absender:
        absender = absender.split("<")[-1].rstrip(">").strip()
    return liste, nachricht_html, _antwort_formular(kennung, absender, nachricht.header.subject)


def _postfach(user_id: str):
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        return resolve_session(conn, user_id, "search_mail", SETTINGS.token_key)
    finally:
        conn.close()


def _liste(user_id: str, gewaehlt: str) -> str:
    try:
        jetzt = time.monotonic()
        zwischengespeichert = _CACHE.get(user_id)
        if zwischengespeichert and jetzt - zwischengespeichert[0] < CACHE_SEKUNDEN:
            kopfzeilen = zwischengespeichert[1]
        else:
            session = _postfach(user_id)
            kopfzeilen = session.provider.search("", limit=MAX_ANZEIGE)
            _CACHE[user_id] = (jetzt, kopfzeilen)
    except (NoMailbox, NotImplementedError) as fehler:
        return f"<p>{fehler}</p>"
    except Exception as fehler:  # noqa: BLE001 - Anzeige statt Absturz
        return f"<p>Das Postfach antwortet nicht: {fehler}</p>"

    if not kopfzeilen:
        return "<p>Der Posteingang ist leer.</p>"

    zeilen = []
    for kopf in kopfzeilen:
        aktiv = ' style="font-weight:600"' if kopf.provider_id == gewaehlt else ""
        zeilen.append(
            f"""
            <tr{aktiv}>
              <td style="padding:0.35rem 0.6rem 0.35rem 0;white-space:nowrap">
                {kopf.received_at.astimezone():%d.%m. %H:%M}
              </td>
              <td style="padding:0.35rem 0.6rem">{kopf.sender}</td>
              <td style="padding:0.35rem 0">
                <a href="/post?nachricht={quote(kopf.provider_id)}"
                   style="color:inherit">{kopf.subject or '(ohne Betreff)'}</a>
              </td>
            </tr>
            """
        )
    return (
        '<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
        '<colgroup><col style="width:6.5rem"><col style="width:14rem"><col></colgroup>'
        f"<tbody>{''.join(zeilen)}</tbody></table>"
    )


def _nachricht(user_id: str, kennung: str) -> str:
    try:
        session = _postfach(user_id)
        nachricht = session.provider.get_message(kennung)
    except Exception as fehler:  # noqa: BLE001 - Anzeige statt Absturz
        return f"<p>Die Nachricht lässt sich nicht lesen: {fehler}</p>"

    text = nachricht.body_text.replace("&", "&amp;").replace("<", "&lt;")
    return f"""
    <p style="margin:0 0 0.5rem 0">
      <strong>{nachricht.header.subject or '(ohne Betreff)'}</strong><br>
      <span style="color:#555">von {nachricht.header.sender}
      am {nachricht.header.received_at.astimezone():%d.%m.%Y %H:%M}</span>
    </p>
    <pre style="white-space:pre-wrap;font-family:inherit;margin:0">{text[:4000]}</pre>
    """


def _antwort_formular(kennung: str, an: str, betreff: str) -> str:
    returnf = betreff if betreff.lower().startswith("re:") else f"Re: {betreff}"
    return f"""
    <form method="post" action="/post/entwurf"
          style="display:flex;flex-direction:column;gap:0.75rem">
      <input type="hidden" name="antwort_auf" value="{kennung}">
      <kol-input-text data-name="an" _label="An" _value="{an}"></kol-input-text>
      <kol-input-text data-name="betreff" _label="Betreff" _value="{returnf}"></kol-input-text>
      <kol-textarea data-name="text" _label="Antwort" _rows="5"></kol-textarea>
      <input type="hidden" name="aktion" id="aktion-wert" value="entwurf">
      <p style="margin:0;color:#555;font-size:0.9em">
        „Entwurf anlegen" legt die Nachricht nur im Postfach ab. „Senden" schickt sie
        sofort — dieser Klick ist Ihre Freigabe.
      </p>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
        <kol-button _label="Senden" _variant="primary"
                    data-feld="aktion" data-wert="senden"></kol-button>
        <kol-button _label="Entwurf anlegen" _variant="secondary"
                    data-feld="aktion" data-wert="entwurf"></kol-button>
      </div>
    </form>
    """


@ui.page("/post", response_timeout=30)
async def mail_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    kennung = request.query_params.get("nachricht", "")
    meldung = request.query_params.get("meldung", "")

    liste, nachricht_html, formular = await asyncio.to_thread(
        _seite, user.subject, kennung
    )

    with layout.content():
        layout.app_frame("Post", user.name or user.email)
        layout.nav("/post")
        if meldung:
            layout.banner(meldung)
        layout.card("Posteingang", liste)
        if nachricht_html:
            layout.card("Nachricht", nachricht_html)
            layout.card("Antwort", formular)


def _entwurf_anlegen(user_id: str, an: str, betreff: str, text: str, antwort_auf: str):
    session = _postfach(user_id)
    return session.provider.create_draft(
        (an,), betreff, text, reply_to=antwort_auf or None
    )


def _senden(user_id: str, entwurf_id: str):
    session = _postfach(user_id)
    return session.provider.send_draft(entwurf_id)


async def entwurf(request: Request):
    """Entwurf im Postfach ablegen; gesendet wird nicht."""
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    an = str(form.get("an", "")).strip()
    betreff = str(form.get("betreff", "")).strip()
    text = str(form.get("text", ""))
    antwort_auf = str(form.get("antwort_auf", "")).strip()
    aktion = str(form.get("aktion", "entwurf"))

    if not an or "@" not in an:
        return RedirectResponse(
            f"/post?meldung={quote('Bitte eine gültige Empfängeradresse eintragen')}",
            status_code=303,
        )

    try:
        entwurf_ref = await asyncio.to_thread(
            _entwurf_anlegen, user.subject, an, betreff or "(ohne Betreff)", text, antwort_auf
        )
    except Exception as fehler:  # noqa: BLE001 - Meldung statt Absturz
        return RedirectResponse(
            f"/post?meldung={quote('Der Entwurf wurde nicht angelegt: ' + str(fehler))}",
            status_code=303,
        )

    if aktion != "senden":
        return RedirectResponse(
            f"/post?meldung={quote('Entwurf angelegt: ' + entwurf_ref.provider_id)}",
            status_code=303,
        )

    # Senden auf Klick des Menschen. Das ist die Freigabe; das Modell sendet nie selbst.
    try:
        ergebnis = await asyncio.to_thread(_senden, user.subject, entwurf_ref.provider_id)
    except Exception as fehler:  # noqa: BLE001 - Meldung statt Absturz
        return RedirectResponse(
            f"/post?meldung={quote('Nicht gesendet: ' + str(fehler))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/post?meldung={quote('Gesendet an ' + an + ' um ' + ergebnis.sent_at.astimezone().strftime('%H:%M:%S'))}",
        status_code=303,
    )


def register(app) -> None:
    app.add_route("/post/entwurf", entwurf, methods=["POST"], name="mail_draft")
