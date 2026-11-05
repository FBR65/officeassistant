"""Seite „Anbindungen": Dienste außerhalb des Postfachs verbinden.

Je Nutzer: Dienst wählen, Adresse und Zugangsschlüssel eintragen, verbinden, trennen.
Fehlende oder nicht mögliche Dienste werden mit Grund genannt (Skype).
"""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.connections import BLOCKED, KINDS, ConnectionError_, ConnectionStore
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

# Welche Felder ein Dienst braucht. Der Schlüssel ist der Spaltenname im Formular.
FELDER: dict[str, tuple[tuple[str, str], ...]] = {
    "jira": (("email", "E-Mail"), ("token", "API-Token")),
    "confluence": (("email", "E-Mail"), ("token", "API-Token")),
    "mattermost": (("token", "Zugangsschlüssel"), ("channel_id", "Kanal (optional)")),
    "sharepoint": (("access_token", "Graph-Token"),),
    "onenote": (("access_token", "Graph-Token"),),
    "webex": (("access_token", "Zugangstoken"),),
}

VORGABE_ADRESSE = {
    "ics": "https://outlook.office365.com/owa/calendar/…/calendar.ics",
    "jira": "https://ihre-firma.atlassian.net",
    "confluence": "https://ihre-firma.atlassian.net/wiki",
    "mattermost": "https://chat.ihre-firma.de",
    "sharepoint": "https://graph.microsoft.com/v1.0",
    "onenote": "https://graph.microsoft.com/v1.0",
    "webex": "https://webexapis.com/v1",
}


def _liste(user_id: str) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        alle = ConnectionStore(conn, SETTINGS.token_key).of_user(user_id)
    finally:
        conn.close()

    if not alle:
        return "<p>Noch keine Anbindung eingerichtet.</p>"

    zeilen = []
    for verbindung in alle:
        zustand = "verbunden" if verbindung.ready else "unvollständig"
        zeilen.append(
            f"""
            <tr>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">{KINDS.get(verbindung.kind, verbindung.kind)}</td>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">{verbindung.base_url}</td>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">{zustand}</td>
              <td style="padding:0.5rem 0;text-align:right">
                <form method="post" action="/anbindungen/{verbindung.id}/trennen">
                  <kol-button _label="Trennen" _variant="secondary"></kol-button>
                </form>
              </td>
            </tr>
            """
        )
    return f"""
    <table style="width:100%;border-collapse:collapse;table-layout:fixed">
      <colgroup><col style="width:34%"><col><col style="width:9rem"><col style="width:9rem"></colgroup>
      <thead>
        <tr style="text-align:left;border-bottom:1px solid #d0d0d0">
          <th style="padding-bottom:0.5rem">Dienst</th>
          <th style="padding-bottom:0.5rem">Adresse</th>
          <th style="padding-bottom:0.5rem">Zustand</th>
          <th></th>
        </tr>
      </thead>
      <tbody>{''.join(zeilen)}</tbody>
    </table>
    """


def _formular() -> str:
    dienste = "".join(f'<option value="{wert}">{label}</option>' for wert, label in KINDS.items())
    # Jedes Feld einmal, mit der Beschriftung des ersten Dienstes, der es braucht.
    beschriftung: dict[str, str] = {}
    for feld_liste in FELDER.values():
        for name, label in feld_liste:
            beschriftung.setdefault(name, label)
    felder = "".join(
        f'<kol-input-text data-name="{name}" _label="{label}" '
        f'_type="{"password" if name in ("token", "access_token") else "text"}"></kol-input-text>'
        for name, label in beschriftung.items()
    )
    return f"""
    <form method="post" action="/anbindungen/speichern"
          style="display:flex;flex-direction:column;gap:1rem;max-width:36rem">
      <label for="kind">Dienst</label>
      <select id="kind" name="kind" style="padding:0.4rem">{dienste}</select>
      <kol-input-text data-name="base_url" _label="Adresse"
                      _placeholder="{VORGABE_ADRESSE['jira']}"></kol-input-text>
      {felder}
      <p style="margin:0;color:#555;font-size:0.9em">
        Der Zugangsschlüssel wird verschlüsselt gespeichert und nur im Dienstprozess
        entschlüsselt. Er erscheint nie im Browser.
      </p>
      <kol-button _label="Verbinden" _variant="primary"></kol-button>
    </form>
    """


def _hinweis() -> str:
    zeilen = "".join(f"<li><strong>{name}</strong>: {grund}</li>" for name, grund in BLOCKED.items())
    return f"<p>Nicht möglich:</p><ul>{zeilen}</ul>"


@ui.page("/anbindungen")
async def connections_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    meldung = request.query_params.get("meldung", "")
    if meldung:
        layout.banner(meldung)

    with layout.content():
        layout.app_frame("Anbindungen", user.name or user.email)
        layout.nav("/anbindungen")
        layout.card("Eingerichtete Anbindungen", _liste(user.subject))
        layout.card("Dienst verbinden", _formular())
        layout.card("Was nicht geht", _hinweis())


async def speichern(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    kind = str(form.get("kind", ""))
    base_url = str(form.get("base_url", "")).strip()
    geheim = {
        name: str(form.get(name, "")).strip()
        for name in ("email", "token", "channel_id", "access_token")
        if str(form.get(name, "")).strip()
    }

    if not base_url:
        return RedirectResponse(
            f"/anbindungen?meldung={quote('Bitte die Adresse des Dienstes eintragen')}",
            status_code=303,
        )

    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        ConnectionStore(conn, SETTINGS.token_key).save(user.subject, kind, base_url, geheim)
    except ValueError as exc:
        return RedirectResponse(f"/anbindungen?meldung={quote(str(exc))}", status_code=303)
    finally:
        conn.close()

    return RedirectResponse(
        f"/anbindungen?meldung={quote('Anbindung gespeichert: ' + KINDS.get(kind, kind))}",
        status_code=303,
    )


async def trennen(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    connection_id = int(request.path_params["connection_id"])
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        ConnectionStore(conn, SETTINGS.token_key).delete(connection_id, user.subject)
    finally:
        conn.close()
    return RedirectResponse(
        f"/anbindungen?meldung={quote('Anbindung getrennt')}", status_code=303
    )


def register(app) -> None:
    app.add_route("/anbindungen/speichern", speichern, methods=["POST"], name="connection_save")
    app.add_route(
        "/anbindungen/{connection_id}/trennen", trennen, methods=["POST"], name="connection_delete"
    )
