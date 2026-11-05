"""Seite „Aufträge": eine Anfrage an den Assistenten schicken und die Antwort sehen.

Der Lauf geht mit dem Token des angemeldeten Nutzers an AgentOS. Hält der Lauf an einer
Freigabe an, verweist die Seite auf „Freigaben".
"""

from __future__ import annotations

import httpx
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from urllib.parse import quote

from officeassistant.settings import Settings
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()
LAST_RUN = "letzter_lauf"
MAX_ANTWORT = 1500



@ui.page("/auftraege")
async def runs_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return
    try:
        user = auth.with_fresh_token(user, await auth.access_token(request, SETTINGS))
    except auth.NotAuthenticated:
        ui.navigate.to("/login")
        return

    with layout.content():
        layout.app_frame("Aufträge", user.name or user.email)
        layout.nav("/auftraege")

        message = request.query_params.get("meldung", "")
        if message:
            layout.banner(message)

        result = request.session.get(LAST_RUN)
        if result:
            _show_result(result)

        layout.card(
            "Neuer Auftrag",
            f"""
            <form method="post" action="/auftraege/starten"
                  style="display:flex;flex-direction:column;gap:1rem">
              <kol-textarea _label="Was soll der Assistent tun?" _rows="4"
                            data-name="auftrag"
                            _placeholder="Zum Beispiel: Welche Mails brauchen heute eine Antwort?"></kol-textarea>
              <input type="hidden" name="auftrag" id="auftrag-wert">
              <div><kol-button _label="Senden" _variant="primary"></kol-button></div>
            </form>
            """,
        )


def _format(text: str) -> str:
    """Einfache Auszeichnung des Modells lesbar machen (fett, kursiv, Zeilen)."""
    sicher = (text or "").replace("&", "&amp;").replace("<", "&lt;")
    for muster, tag in (("**", "strong"), ("*", "em")):
        teile = sicher.split(muster)
        if len(teile) > 2:
            sicher = "".join(
                teil if i % 2 == 0 else f"<{tag}>{teil}</{tag}>"
                for i, teil in enumerate(teile)
            )
    return sicher.replace("\n", "<br>")


def _show_result(result: dict) -> None:
    status = result.get("status", "")
    if status == "PAUSED":
        body = (
            "<p>Der Lauf wartet auf eine Freigabe.</p>"
            '<p><a href="/freigaben">Zu den Freigaben</a></p>'
        )
    else:
        body = f"<p>{_format(str(result.get('content') or ''))}</p>"
    layout.card(f"Letzte Antwort ({status or 'unbekannt'})", body)


async def start_run(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    auftrag = str(form.get("auftrag", "")).strip()
    if not auftrag:
        return RedirectResponse(
            f"/auftraege?meldung={quote('Bitte einen Auftrag eintragen')}", status_code=303
        )

    try:
        token = await auth.access_token(request, SETTINGS)
    except auth.NotAuthenticated:
        return RedirectResponse("/login", status_code=303)

    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{SETTINGS.api_base_url}/agents/{SETTINGS.agent_id}/runs",
            headers={"Authorization": f"Bearer {token}"},
            data={"message": auftrag, "stream": "false", "user_id": user.subject},
        )
    if response.status_code >= 400:
        return RedirectResponse(
            f"/auftraege?meldung={quote('Der Assistent antwortete mit Fehler ' + str(response.status_code))}",
            status_code=303,
        )

    body = response.json()
    request.session[LAST_RUN] = {
        "status": str(body.get("status", "")),
        "content": str(body.get("content", ""))[:MAX_ANTWORT],
        "run_id": str(body.get("run_id", "")),
        "session_id": str(body.get("session_id", "")),
    }
    return RedirectResponse("/auftraege", status_code=303)


def register(app) -> None:
    app.add_route("/auftraege/starten", start_run, methods=["POST"], name="run_start")
