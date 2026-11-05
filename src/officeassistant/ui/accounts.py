"""Seite „Postfächer": anzeigen, verbinden, trennen.

Zugangsdaten liegen verschlüsselt in der Datenbank. Die Seite zeigt nur Adresse,
Anbieter und Zustand — niemals Token.
"""

from __future__ import annotations

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from urllib.parse import quote

from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.tokens import TokenStore
from officeassistant.store.users import UserStore
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()


PROVIDERS = {
    "gmail": "Gmail (App-Kennwort)",
    "imap": "Exchange on-prem / IMAP",
    "fake": "Testpostfach (ohne Netzzugriff)",
}

STATUS = {
    "active": "aktiv",
    "expired": "abgelaufen",
    "revoked": "widerrufen",
}

# KoliBri-Knöpfe sind keine <button>-Elemente und senden kein Formular ab.
# Deshalb löst der Klick ausdrücklich das Absenden aus.


# KoliBri-Felder liegen im Shadow DOM; der Wert wird beim Klick gelesen und
# in das versteckte Feld geschrieben, dann das Formular abgeschickt.
CONNECT_JS = """const f=this.closest('form');const el=document.querySelector('kol-input-text');(async()=>{f.elements.adresse.value=(typeof el.getValue==='function')?await el.getValue():'';f.requestSubmit();})()"""


def _accounts(user_id: str):
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        return TokenStore(conn, SETTINGS.token_key).accounts(user_id)
    finally:
        conn.close()


@ui.page("/postfaecher")
async def accounts_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    with layout.content():
        layout.app_frame("Postfächer", user.name or user.email)
        layout.nav("/postfaecher")
        _body(request, user)


def _body(request: Request, user) -> None:
    message = request.query_params.get("meldung", "")
    if message:
        layout.banner(message)

    rows = "".join(
        f"""
        <tr>
          <td style="padding:0.5rem 1rem 0.5rem 0">{account.address}</td>
          <td style="padding:0.5rem 1rem">{PROVIDERS.get(account.provider, account.provider)}</td>
          <td style="padding:0.5rem 1rem">{STATUS.get(account.status, account.status)}</td>
          <td style="padding:0.5rem 0">
            <form method="post" action="/postfaecher/{account.id}/trennen">
              <kol-button _label="Trennen" _variant="secondary"></kol-button>
            </form>
          </td>
        </tr>
        """
        for account in _accounts(user.subject)
    )
    body = (
        f"""
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="text-align:left;border-bottom:1px solid #d0d0d0">
              <th style="padding-bottom:0.5rem">Adresse</th>
              <th style="padding-bottom:0.5rem">Anbieter</th>
              <th style="padding-bottom:0.5rem">Zustand</th>
              <th></th>
            </tr>
          </thead>
          <tbody>{rows or '<tr><td colspan="4">Noch kein Postfach verbunden.</td></tr>'}</tbody>
        </table>
        """
    )
    layout.card("Verbundene Postfächer", body)

    options = "".join(
        f'<option value="{key}">{label}</option>' for key, label in PROVIDERS.items()
    )
    layout.card(
        "Postfach verbinden",
        f"""
        <form method="post" action="/postfaecher/verbinden"
              style="display:flex;flex-direction:column;gap:1rem;max-width:32rem">
          <label for="anbieter">Anbieter</label>
          <select id="anbieter" name="anbieter" style="padding:0.4rem">{options}</select>
          <kol-input-text _label="Adresse" _type="email" data-name="adresse"
                          _placeholder="name@example.org"></kol-input-text>
          <p style="margin:0;color:#555">Nur für Exchange on-prem oder einen anderen
             IMAP-Server ausfüllen:</p>
          <kol-input-text _label="IMAP-Server" data-name="host"
                          _placeholder="mail.example.org"></kol-input-text>
          <kol-input-text _label="IMAP-Port" _type="number" data-name="port"
                          _placeholder="993"></kol-input-text>
          <kol-input-text _label="Benutzername" data-name="user"></kol-input-text>
          <kol-input-text _label="Kennwort" _type="password" data-name="password"></kol-input-text>
          <kol-input-text _label="Absendername (für ausgehende Nachrichten)"
                          data-name="display_name"
                          _placeholder="Emil Mazdarati"></kol-input-text>
          <label for="verschluesselung">Verschlüsselung</label>
          <select id="verschluesselung" name="verschluesselung" style="padding:0.4rem">
            <option value="ssl">IMAP über TLS (üblich)</option>
            <option value="starttls">Ohne TLS beim Abholen, SMTP mit STARTTLS</option>
            <option value="keine">Ohne Verschlüsselung (nur Testserver)</option>
          </select>
          <kol-input-text _label="SMTP-Server" data-name="smtp_host"
                          _placeholder="mail.example.org"></kol-input-text>
          <kol-input-text _label="SMTP-Port" _type="number" data-name="smtp_port"
                          _placeholder="587"></kol-input-text>
          <kol-button _label="Verbinden" _variant="primary"></kol-button>
        </form>
        """,
    )
    # KoliBri-Felder liegen im Shadow DOM und werden vom Formular nicht erfasst.
    # Der Wert wird deshalb in ein verstecktes Feld gespiegelt (NiceGUI erlaubt
    # <script> nicht in ui.html).


async def connect_account(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    provider = str(form.get("anbieter", ""))
    address = str(form.get("adresse", "")).strip()
    payload = {
        feld: str(form.get(feld, "")).strip()
        for feld in (
            "host",
            "port",
            "user",
            "password",
            "smtp_host",
            "smtp_port",
            "display_name",
        )
        if str(form.get(feld, "")).strip()
    }
    verschluesselung = str(form.get("verschluesselung", "ssl"))
    payload["ssl"] = "true" if verschluesselung == "ssl" else "false"
    payload["smtp_security"] = {
        "ssl": "starttls",
        "starttls": "starttls",
        "keine": "none",
    }.get(verschluesselung, "starttls")

    if not address:
        return RedirectResponse(
            f"/postfaecher?meldung={quote('Bitte eine Adresse eintragen')}", status_code=303
        )
    if provider not in PROVIDERS:
        return RedirectResponse(
            f"/postfaecher?meldung={quote('Diesen Anbieter gibt es nicht')}", status_code=303
        )
    if "@" not in address:
        return RedirectResponse(
            f"/postfaecher?meldung={quote('Die Adresse enthält kein @')}", status_code=303
        )

    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        # Beim ersten angemeldeten Zugriff entsteht der Nutzer; die Anmeldung selbst
        # kennt keine Datenbank.
        UserStore(conn).upsert(user.subject, user.email, user.name or user.email)
        if provider == "gmail":
            if "password" not in payload:
                return RedirectResponse(
                    f"/postfaecher?meldung={quote('Für Gmail fehlt das App-Kennwort')}",
                    status_code=303,
                )
        if provider == "imap":
            fehlend = [feld for feld in ("host", "user", "password") if feld not in payload]
            if fehlend:
                return RedirectResponse(
                    f"/postfaecher?meldung={quote('Für IMAP fehlen: ' + ', '.join(fehlend))}",
                    status_code=303,
                )
        TokenStore(conn, SETTINGS.token_key).save(user.subject, provider, address, payload)
    finally:
        conn.close()
    return RedirectResponse(f"/postfaecher?meldung={quote('Postfach verbunden')}", status_code=303)


async def disconnect_account(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    account_id = int(request.path_params["account_id"])
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        store = TokenStore(conn, SETTINGS.token_key)
        mine = {account.id for account in store.accounts(user.subject)}
        if account_id not in mine:
            return RedirectResponse(
                f"/postfaecher?meldung={quote('Dieses Postfach gehört nicht zu Ihrem Konto')}",
                status_code=303,
            )
        store.delete(account_id)
    finally:
        conn.close()
    return RedirectResponse(f"/postfaecher?meldung={quote('Postfach getrennt')}", status_code=303)


def register(app) -> None:
    app.add_route(
        "/postfaecher/verbinden", connect_account, methods=["POST"], name="account_connect"
    )
    app.add_route(
        "/postfaecher/{account_id}/trennen",
        disconnect_account,
        methods=["POST"],
        name="account_disconnect",
    )
