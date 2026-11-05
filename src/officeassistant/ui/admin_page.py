"""Seite „Verwaltung": Nutzer anlegen, Rolle setzen, Zugang sperren.

Nur sichtbar und erreichbar für `admin` und `owner`. Wer die Seite aufruft, ohne diese
Rolle zu haben, erhält 403 mit einem Satz, der den Grund nennt.

Der angelegte Nutzer entsteht über Keycloak (das Verzeichnis), danach als Zeile in
`app_user`. Jede Änderung schreibt eine Zeile ins Protokoll.
"""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from officeassistant.connectors.keycloak_admin import KeycloakAdmin, KeycloakError, NeuerNutzer
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.audit import AuditLog
from officeassistant.store.users import ROLES, UserStore
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

ROLLEN_TEXT = {"member": "Nutzer", "admin": "Verwaltung", "owner": "Eigentümer"}

# KoliBri erwartet die Auswahl als JSON-Text im Attribut `_options`.
ROLLEN_OPTIONEN = (
    '<option value="member">Nutzer</option>'
    '<option value="admin">Verwaltung</option>'
)


def _verbindung():
    return db.connect(SETTINGS.db_url, autocommit=True)


def _darf_verwalten(conn, subject: str) -> bool:
    """Nur `admin` und `owner` dürfen diese Seite sehen und bedienen."""
    eigener = UserStore(conn).get(subject)
    return bool(eigener and eigener.is_admin)


def _tabelle(users: list) -> str:
    """Ein Block je Nutzer.

    Eine Tabelle mit fünf Spalten wird im schmalen Rahmen zusammengedrückt; die
    Beschriftungen brechen dann mitten im Wort. Blöcke bleiben lesbar.
    """
    if not users:
        return "<p>Noch kein Nutzer angemeldet.</p>"

    bloecke = []
    for user in users:
        stand = "aktiv" if user.active else "gesperrt"
        name = user.display_name or "ohne Namen"
        bloecke.append(
            f"""
            <div style="border-top:1px solid #eee;padding:0.9rem 0">
              <div style="font-size:1.05em"><strong>{name}</strong></div>
              <div style="color:#555">{user.email}</div>
              <div style="margin:0.3rem 0 0.6rem 0">
                Rolle: {ROLLEN_TEXT.get(user.role, user.role)} · {stand}
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:0.6rem;align-items:flex-end">
                <form method="post" action="/verwaltung/{user.id}/rolle"
                      style="display:flex;gap:0.4rem;align-items:flex-end;flex-wrap:wrap">
                  <label for="rolle-{user.id}" style="font-size:0.9em;color:#555">Neue Rolle</label>
                  <select id="rolle-{user.id}" name="rolle" style="padding:0.35rem">
                    {ROLLEN_OPTIONEN}
                  </select>
                  <kol-button _label="Rolle setzen" _variant="secondary"></kol-button>
                </form>
                <form method="post" action="/verwaltung/{user.id}/zugang">
                  <input type="hidden" name="aktiv" value="{'0' if user.active else '1'}">
                  <kol-button _label="{'Sperren' if user.active else 'Freigeben'}"
                              _variant="secondary"></kol-button>
                </form>
              </div>
            </div>
            """
        )
    return "".join(bloecke)


def _formular() -> str:
    return f"""
    <form method="post" action="/verwaltung/anlegen" style="display:grid;gap:1rem">
      <kol-input-text _label="Anzeigename" data-name="anzeigename" _required="true"></kol-input-text>
      <kol-input-email _label="E-Mail" data-name="email" _required="true"></kol-input-email>
      <kol-input-text _label="Anmeldename" data-name="benutzername" _required="true"></kol-input-text>
      <kol-input-text _label="Startkennwort" data-name="passwort" _type="password"
                      _required="true"></kol-input-text>
      <label for="rolle">Rolle</label>
      <select id="rolle" name="rolle" style="padding:0.4rem">{ROLLEN_OPTIONEN}</select>
      <div><kol-button _label="Nutzer anlegen" _variant="primary"></kol-button></div>
    </form>
    """


@ui.page("/verwaltung")
async def verwaltung(request: Request) -> Response | None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    conn = _verbindung()
    try:
        if not _darf_verwalten(conn, user.subject):
            return Response(
                "<h1>Verwaltung</h1><p>Diese Seite ist der Verwaltung vorbehalten.</p>"
                '<p><a href="/">Zur Übersicht</a></p>',
                status_code=403,
                media_type="text/html; charset=utf-8",
            )
        alle = UserStore(conn).all_users()
    finally:
        conn.close()

    meldung = request.query_params.get("meldung", "")
    with layout.content():
        layout.app_frame("Verwaltung", user.name or user.email)
        layout.nav("/verwaltung")
        if meldung:
            layout.banner(meldung)
        layout.card("Nutzer", _tabelle(alle))
        layout.card("Nutzer anlegen", _formular())
    return None


async def anlegen(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    formular = await request.form()
    anzeigename = str(formular.get("anzeigename", "")).strip()
    email = str(formular.get("email", "")).strip()
    benutzername = str(formular.get("benutzername", "")).strip()
    passwort = str(formular.get("passwort", ""))
    rolle = str(formular.get("rolle", "member")).strip() or "member"

    conn = _verbindung()
    try:
        if not _darf_verwalten(conn, user.subject):
            return Response("Diese Seite ist der Verwaltung vorbehalten.", status_code=403)

        fehlt = [
            name
            for name, wert in (
                ("Anzeigename", anzeigename),
                ("E-Mail", email),
                ("Anmeldename", benutzername),
                ("Startkennwort", passwort),
            )
            if not wert
        ]
        if fehlt:
            return RedirectResponse(
                "/verwaltung?meldung=" + quote("Bitte ausfüllen: " + ", ".join(fehlt)),
                status_code=303,
            )

        try:
            kennung = KeycloakAdmin(
                SETTINGS.oidc_issuer,
                SETTINGS.keycloak_realm,
                SETTINGS.keycloak_admin_user,
                SETTINGS.keycloak_admin_password,
            ).create_user(
                NeuerNutzer(
                    benutzername=benutzername,
                    email=email,
                    anzeigename=anzeigename,
                    passwort=passwort,
                )
            )
        except KeycloakError as fehler:
            return RedirectResponse(
                "/verwaltung?meldung=" + quote(str(fehler)), status_code=303
            )

        UserStore(conn).upsert(kennung, email, anzeigename, rolle if rolle in ROLES else "member")
        AuditLog(conn).append(
            user.subject, "verwaltung.nutzer_angelegt", {"ziel": kennung, "rolle": rolle}, "ok"
        )
        return RedirectResponse(
            "/verwaltung?meldung=" + quote(f"Nutzer angelegt: {benutzername}"),
            status_code=303,
        )
    finally:
        conn.close()


async def rolle(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ziel = str(request.path_params.get("user_id", ""))
    formular = await request.form()
    rolle = str(formular.get("rolle", "")).strip()

    conn = _verbindung()
    try:
        store = UserStore(conn)
        if not _darf_verwalten(conn, user.subject):
            return Response("Diese Seite ist der Verwaltung vorbehalten.", status_code=403)
        if ziel == user.subject:
            return RedirectResponse(
                "/verwaltung?meldung=" + quote("Die eigene Rolle lässt sich nicht ändern."),
                status_code=303,
            )
        if rolle not in ROLES:
            return RedirectResponse(
                "/verwaltung?meldung=" + quote("Unbekannte Rolle."), status_code=303
            )
        store.set_role(ziel, rolle)
        AuditLog(conn).append(user.subject, "verwaltung.rolle_gesetzt", {"ziel": ziel, "rolle": rolle}, "ok")
        return RedirectResponse(
            "/verwaltung?meldung=" + quote("Rolle gesetzt."), status_code=303
        )
    finally:
        conn.close()


async def zugang(request: Request) -> Response:
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ziel = str(request.path_params.get("user_id", ""))
    formular = await request.form()
    aktiv = str(formular.get("aktiv", "1")) == "1"

    conn = _verbindung()
    try:
        store = UserStore(conn)
        if not _darf_verwalten(conn, user.subject):
            return Response("Diese Seite ist der Verwaltung vorbehalten.", status_code=403)
        if ziel == user.subject:
            return RedirectResponse(
                "/verwaltung?meldung=" + quote("Das eigene Konto lässt sich nicht sperren."),
                status_code=303,
            )
        store.set_active(ziel, aktiv)
        AuditLog(conn).append(
            user.subject,
            "verwaltung.zugang_gesetzt",
            {"ziel": ziel, "aktiv": aktiv},
            "ok",
        )
        return RedirectResponse(
            "/verwaltung?meldung="
            + quote("Zugang freigegeben." if aktiv else "Zugang gesperrt."),
            status_code=303,
        )
    finally:
        conn.close()


def register(app) -> None:
    """Formulare schicken POST; NiceGUI-Seiten beantworten nur GET."""
    app.add_route("/verwaltung/anlegen", anlegen, methods=["POST"], name="verwaltung_anlegen")
    app.add_route(
        "/verwaltung/{user_id}/rolle", rolle, methods=["POST"], name="verwaltung_rolle"
    )
    app.add_route(
        "/verwaltung/{user_id}/zugang", zugang, methods=["POST"], name="verwaltung_zugang"
    )
