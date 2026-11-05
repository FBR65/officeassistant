"""Seite „Kalender": eine Woche mit den Terminen aus der ICS-Quelle.

Quelle: eine Anbindung der Art `ics` (Abonnement-Adresse oder Datei). Microsoft Graph ist
vorbereitet und liefert erst mit Mandant und Zustimmung Termine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request

from officeassistant.calendar.ics import CalendarError, woche
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.connections import ConnectionError_, ConnectionStore
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

WOCHENTAG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _quelle(user_id: str) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        return ConnectionStore(conn, SETTINGS.token_key).one(user_id, "ics").base_url
    finally:
        conn.close()


def _inhalt(user_id: str, versatz: int) -> tuple[str, str]:
    """Kopfzeile und Tabelle der Woche; `versatz` zählt Wochen ab heute."""
    try:
        quelle = _quelle(user_id)
    except ConnectionError_ as fehler:
        return str(fehler), ""

    bezug = datetime.now(UTC) + timedelta(weeks=versatz)
    try:
        montag, sonntag, alle = woche(quelle, bezug)
    except CalendarError as fehler:
        return str(fehler), ""

    kopf = (
        f"Woche vom {montag:%d.%m.%Y} bis {(sonntag - timedelta(days=1)):%d.%m.%Y}"
    )

    tage = []
    for nummer in range(7):
        tag = montag + timedelta(days=nummer)
        des_tages = [termin for termin in alle if termin.beginn.date() == tag.date()]
        if des_tages:
            eintraege = "".join(
                f"""
                <li style="margin:0.15rem 0">
                  <strong>{'ganztägig' if termin.ganztags else termin.beginn.astimezone().strftime('%H:%M')}</strong>
                  {' – ' + termin.ende.astimezone().strftime('%H:%M') if not termin.ganztags else ''}
                  {termin.titel}
                  {f'<span style="color:#555"> · {termin.ort}</span>' if termin.ort else ''}
                </li>
                """
                for termin in des_tages
            )
        else:
            eintraege = '<span style="color:#777">keine Termine</span>'
        tage.append(
            f"""
            <tr>
              <td style="padding:0.4rem 0.8rem 0.4rem 0;vertical-align:top;white-space:nowrap">
                <strong>{WOCHENTAG[nummer]}</strong><br>
                <span style="color:#555">{tag:%d.%m.}</span>
              </td>
              <td style="padding:0.4rem 0"><ul style="margin:0;padding-left:1.1rem">{eintraege}</ul></td>
            </tr>
            """
        )

    tabelle = (
        '<table style="width:100%;border-collapse:collapse">'
        f"<tbody>{''.join(tage)}</tbody></table>"
    )
    return kopf, tabelle


@ui.page("/kalender")
async def calendar_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    try:
        versatz = int(request.query_params.get("woche", "0"))
    except ValueError:
        versatz = 0

    kopf, tabelle = _inhalt(user.subject, versatz)

    with layout.content():
        layout.app_frame("Kalender", user.name or user.email)
        layout.nav("/kalender")
        ui.html(
            f"""
            <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap">
              <kol-button _label="Vorige Woche" _variant="secondary"
                          data-href="/kalender?woche={versatz - 1}"></kol-button>
              <kol-button _label="Diese Woche" _variant="secondary"
                          data-href="/kalender?woche=0"></kol-button>
              <kol-button _label="Nächste Woche" _variant="secondary"
                          data-href="/kalender?woche={versatz + 1}"></kol-button>
              <span style="color:#555">{kopf}</span>
            </div>
            """,
            sanitize=False,
        ).classes("w-full")

        if tabelle:
            layout.card(kopf, tabelle)
        else:
            layout.card(
                "Kalender",
                f"<p>{kopf}</p><p>Quelle einrichten: Seite "
                f"<a href='/anbindungen'>Anbindungen</a>, Dienst „Kalender — ICS-Abo oder Datei“.</p>",
            )


def register(app) -> None:
    """Seite meldet sich über den Dekorator an."""
