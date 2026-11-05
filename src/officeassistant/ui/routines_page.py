"""Seite „Routinen": Zeitplan, Vertrauensstufe, Läufe und ein Editor (P4.6).

Ein Nutzer legt Routinen hier an, ändert sie, schaltet sie ab und löscht sie. Der Zeitplan
wird in Alltagssprache gewählt („Werktags um 8:00"); ein Cron-Ausdruck kommt in der
Oberfläche nicht vor.
Die Läufe entstehen durch den Zeitgeber (`systemd` ruft `scripts/run_routine.py --due`).
"""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from officeassistant.routines.schedule import ARTEN, WOCHENTAGE, ScheduleError, describe
from officeassistant.routines.schedule import cron_from_choice
from officeassistant.routines.store import (
    ROUTINE_NAMES,
    SCOPES,
    TRUST_FOR_SCOPE,
    delete_routine,
    last_runs,
    list_routines,
    save_routine,
    set_enabled,
)
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

TRUST = {
    "read-only": "nur lesen",
    "approval-required": "mit Freigabe",
    "autonomous": "selbsttätig",
}

STATUS = {
    "running": "läuft",
    "completed": "fertig",
    "paused": "wartet auf Freigabe",
    "failed": "gescheitert",
}

def _routinen(user_id: str) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        alle = list_routines(conn, user_id)
    finally:
        conn.close()

    if not alle:
        return "<p>Noch keine Routine eingerichtet.</p>"

    zeilen = []
    for routine in alle:
        beschriftung = "ausschalten" if routine.enabled else "einschalten"
        zeilen.append(
            f"""
            <tr>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">
                {ROUTINE_NAMES.get(routine.name, routine.name)}
                <div style="color:#555;font-size:0.9em">{routine.prompt[:70]}</div>
              </td>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">{describe(routine.cron)}</td>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">
                {SCOPES.get(routine.scope, routine.scope)}
              </td>
              <td style="padding:0.5rem 0.5rem 0.5rem 0">{'aktiv' if routine.enabled else 'aus'}</td>
              <td style="padding:0.5rem 0">
                <form method="post" action="/routinen/{routine.id}/schalten"
                      style="display:inline">
                  <input type="hidden" name="an" value="{'0' if routine.enabled else '1'}">
                  <kol-button _label="{beschriftung}" _variant="secondary"></kol-button>
                </form>
                <form method="post" action="/routinen/{routine.id}/loeschen"
                      style="display:inline;margin-left:0.5rem">
                  <kol-button _label="Löschen" _variant="danger"
                              style="margin-top:0.25rem"></kol-button>
                </form>
              </td>
            </tr>
            """
        )

    return f"""
    <table style="width:100%;border-collapse:collapse;table-layout:fixed">
      <colgroup>
        <col style="width:34%"><col style="width:20%"><col style="width:13%">
        <col style="width:10%"><col style="width:23%">
      </colgroup>
      <thead>
        <tr style="text-align:left;border-bottom:1px solid #d0d0d0">
          <th style="padding-bottom:0.5rem;padding-right:0.5rem">Routine</th>
          <th style="padding-bottom:0.5rem">Zeitplan</th>
          <th style="padding-bottom:0.5rem">Darf</th>
          <th style="padding-bottom:0.5rem;white-space:nowrap">Zustand</th>
          <th></th>
        </tr>
      </thead>
      <tbody>{''.join(zeilen)}</tbody>
    </table>
    """


def _editor() -> str:
    arten = "".join(f'<option value="{wert}">{label}</option>' for wert, label in ARTEN)
    tage = "".join(
        f'<option value="{wert}"{" selected" if wert == "1" else ""}>{label}</option>'
        for wert, label in WOCHENTAGE
    )
    befugnisse = "".join(
        f'<option value="{wert}">{label}</option>' for wert, label in SCOPES.items()
    )
    return f"""
    <form method="post" action="/routinen/speichern"
          style="display:flex;flex-direction:column;gap:1rem;max-width:36rem">
      <kol-input-text data-name="name" _label="Name"
                      _placeholder="z. B. Wochenbericht"></kol-input-text>

      <label for="art">Wie oft?</label>
      <select id="art" name="art" style="padding:0.4rem">{arten}</select>

      <kol-input-text data-name="uhrzeit" _label="Uhrzeit (HH:MM)"
                      _value="08:00"></kol-input-text>

      <label for="wochentag">Wochentag (gilt nur bei An einem Wochentag)</label>
      <select id="wochentag" name="wochentag" style="padding:0.4rem">{tage}</select>

      <kol-input-text data-name="monatstag" _label="Tag im Monat (gilt nur bei Einmal im Monat)"
                      _value="1"></kol-input-text>

      <kol-input-text data-name="abstand" _label="Abstand in Minuten oder Stunden"
                      _value="30"></kol-input-text>

      <kol-textarea data-name="prompt" _label="Was soll die Routine tun?"
                    _rows="4"
                    _placeholder="Fasse jeden Freitag die wichtigsten Nachrichten der Woche
                                  zusammen."></kol-textarea>

      <label for="scope">Was darf die Routine?</label>
      <select id="scope" name="scope" style="padding:0.4rem">{befugnisse}</select>
      <p style="margin:0;color:#555;font-size:0.9em">
        Senden ist in keiner Stufe enthalten. Nachrichten gehen erst hinaus, wenn ein
        Mensch sie freigibt.
      </p>

      <kol-button _label="Routine speichern" _variant="primary"></kol-button>
    </form>
    """


def _laeufe(user_id: str) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        eintraege = last_runs(conn, user_id, limit=5)
    finally:
        conn.close()

    if not eintraege:
        return "<p>Noch kein Lauf.</p>"

    teile = []
    for eintrag in eintraege:
        text = (eintrag.get("output") or eintrag.get("error") or "").strip()
        text = text[:1200].replace("&", "&amp;").replace("<", "&lt;")
        name = ROUTINE_NAMES.get(str(eintrag["name"]), str(eintrag["name"]))
        teile.append(
            f"""
            <div style="margin-bottom:1rem">
              <p style="margin:0 0 0.25rem 0">
                <strong>{name}</strong> ·
                {STATUS.get(str(eintrag['status']), str(eintrag['status']))} ·
                {eintrag['started_at']:%Y-%m-%d %H:%M}
              </p>
              <pre style="white-space:pre-wrap;margin:0;font-family:inherit">{text}</pre>
            </div>
            """
        )
    return "".join(teile)


@ui.page("/routinen")
async def routines_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    meldung = request.query_params.get("meldung", "")
    if meldung:
        layout.banner(meldung)

    with layout.content():
        layout.app_frame("Routinen", user.name or user.email)
        layout.nav("/routinen")
        layout.card("Eingerichtete Routinen", _routinen(user.subject))
        layout.card("Routine anlegen oder ändern", _editor())
        layout.card("Letzte Läufe", _laeufe(user.subject))


async def save(request: Request):
    """Routine speichern; gleicher Name überschreibt die bestehende Fassung."""
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    name = str(form.get("name", "")).strip().lower().replace(" ", "-")
    prompt = str(form.get("prompt", "")).strip()
    scope = str(form.get("scope", "read"))
    trust = TRUST_FOR_SCOPE.get(scope, "approval-required")

    if not name or not prompt:
        return RedirectResponse(
            f"/routinen?meldung={quote('Name und Auftrag dürfen nicht leer sein')}",
            status_code=303,
        )

    try:
        cron = cron_from_choice(
            str(form.get("art", "werktags")),
            uhrzeit=str(form.get("uhrzeit", "")),
            wochentag=str(form.get("wochentag", "1")),
            monatstag=str(form.get("monatstag", "1")),
            abstand=str(form.get("abstand", "")),
        )
    except ScheduleError as exc:
        return RedirectResponse(f"/routinen?meldung={quote(str(exc))}", status_code=303)

    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        try:
            routine = save_routine(conn, user.subject, name, cron, prompt, trust, scope)
        except ValueError as exc:
            return RedirectResponse(f"/routinen?meldung={quote(str(exc))}", status_code=303)
    finally:
        conn.close()

    return RedirectResponse(
        f"/routinen?meldung={quote('Routine gespeichert: ' + routine.name + ' (' + SCOPES.get(routine.scope, routine.scope) + ')')}",
        status_code=303,
    )


async def toggle(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    an = str(form.get("an", "1")) == "1"
    routine_id = int(request.path_params["routine_id"])
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        set_enabled(conn, routine_id, user.subject, an)
    finally:
        conn.close()
    return RedirectResponse(
        f"/routinen?meldung={quote('Routine eingeschaltet' if an else 'Routine ausgeschaltet')}",
        status_code=303,
    )


async def remove(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    routine_id = int(request.path_params["routine_id"])
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        delete_routine(conn, routine_id, user.subject)
    finally:
        conn.close()
    return RedirectResponse(f"/routinen?meldung={quote('Routine gelöscht')}", status_code=303)


def register(app) -> None:
    app.add_route("/routinen/speichern", save, methods=["POST"], name="routine_save")
    app.add_route(
        "/routinen/{routine_id}/schalten", toggle, methods=["POST"], name="routine_toggle"
    )
    app.add_route(
        "/routinen/{routine_id}/loeschen", remove, methods=["POST"], name="routine_delete"
    )
