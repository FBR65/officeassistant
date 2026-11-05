"""Seite „Gedächtnis": was der Assistent über den Nutzer weiß (P4.7).

Einträge sind sichtbar, ergänzbar und löschbar. Sie gelten nur für den angemeldeten Nutzer
und gehen als Anweisung in jeden Lauf.
"""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from officeassistant.settings import Settings
from officeassistant.store import db, memory
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()


def _liste(user_id: str) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        alle = memory.entries(conn, user_id)
    finally:
        conn.close()

    if not alle:
        return "<p>Noch nichts gemerkt. Der Assistent merkt sich Korrekturen selbst; Sie können hier auch selbst etwas ergänzen.</p>"

    zeilen = "".join(
        f"""
        <tr>
          <td style="padding:0.5rem 0.5rem 0.5rem 0">{memory.KINDS.get(eintrag.kind, eintrag.kind)}</td>
          <td style="padding:0.5rem 0.5rem 0.5rem 0">{eintrag.text}</td>
          <td style="padding:0.5rem 0;text-align:right">
            <form method="post" action="/gedaechtnis/{eintrag.id}/loeschen">
              <kol-button _label="Löschen" _variant="secondary"></kol-button>
            </form>
          </td>
        </tr>
        """
        for eintrag in alle
    )
    return f"""
    <table style="width:100%;border-collapse:collapse;table-layout:fixed">
      <colgroup><col style="width:22%"><col><col style="width:9rem"></colgroup>
      <thead>
        <tr style="text-align:left;border-bottom:1px solid #d0d0d0">
          <th style="padding-bottom:0.5rem">Art</th>
          <th style="padding-bottom:0.5rem">Merksatz</th>
          <th></th>
        </tr>
      </thead>
      <tbody>{zeilen}</tbody>
    </table>
    """


def _formular() -> str:
    arten = "".join(f'<option value="{wert}">{label}</option>' for wert, label in memory.KINDS.items())
    return f"""
    <form method="post" action="/gedaechtnis/merken"
          style="display:flex;flex-direction:column;gap:1rem;max-width:36rem">
      <label for="art">Art</label>
      <select id="art" name="art" style="padding:0.4rem">{arten}</select>
      <kol-textarea data-name="text" _label="Merksatz" _rows="3"
                    _placeholder="Herr Reis möchte Anreden ohne Vornamen."></kol-textarea>
      <kol-button _label="Merken" _variant="primary"></kol-button>
    </form>
    """


@ui.page("/gedaechtnis")
async def memory_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    meldung = request.query_params.get("meldung", "")
    if meldung:
        layout.banner(meldung)

    with layout.content():
        layout.app_frame("Gedächtnis", user.name or user.email)
        layout.nav("/gedaechtnis")
        layout.card("Gemerkte Sätze", _liste(user.subject))
        layout.card("Etwas merken", _formular())


async def merken(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    text = str(form.get("text", ""))
    art = str(form.get("art", "other"))

    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        try:
            memory.remember(conn, user.subject, text, art, source="ui")
        except ValueError as exc:
            return RedirectResponse(f"/gedaechtnis?meldung={quote(str(exc))}", status_code=303)
    finally:
        conn.close()
    return RedirectResponse(
        f"/gedaechtnis?meldung={quote('Gemerkt.')}", status_code=303
    )


async def loeschen(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    memory_id = int(request.path_params["memory_id"])
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        memory.forget(conn, memory_id, user.subject)
    finally:
        conn.close()
    return RedirectResponse(
        f"/gedaechtnis?meldung={quote('Gelöscht.')}", status_code=303
    )


def register(app) -> None:
    app.add_route("/gedaechtnis/merken", merken, methods=["POST"], name="memory_add")
    app.add_route(
        "/gedaechtnis/{memory_id}/loeschen",
        loeschen,
        methods=["POST"],
        name="memory_delete",
    )
