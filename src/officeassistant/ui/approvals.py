"""Freigaben (P2.3): Liste offener Entscheidungen und Auflösung über das Dienstkonto.

Ablauf je Entscheidung:
1. Die Oberfläche liest die Freigabe mit dem Token des angemeldeten Nutzers. Fremde
   Freigaben liefern 404 und werden nicht angezeigt.
2. Erst dann löst ein Dienstkonto mit `approvals:write` auf.
3. Der Lauf wird mit dem Nutzer-Token fortgesetzt; `session_id` ist Pflicht.
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.ui import auth, layout
from officeassistant.ui.agentapi import AgentApi, NoApprover, NotYours

SETTINGS = Settings.load()

TOOLS = {
    "send_draft": "Entwurf senden",
    "create_draft": "Entwurf anlegen",
    "label_mail": "Label setzen",
    "archive_mail": "Archivieren",
    "delete": "Löschen",
}

STATUS = {
    "pending": "wartet auf Entscheidung",
    "approved": "freigegeben",
    "rejected": "abgelehnt",
    "expired": "abgelaufen",
    "cancelled": "zurückgezogen",
}

FIELDS = {
    "draft_id": "Entwurf",
    "message_id": "Nachricht",
    "label": "Label",
}
API = AgentApi(base_url=SETTINGS.api_base_url, approver_token=SETTINGS.approver_token)



def _arguments(args: dict) -> str:
    """Argumente lesbar machen statt als Python-Wörterbuch zu zeigen."""
    if not args:
        return "keine weiteren Angaben"
    parts = [f"{FIELDS.get(key, key)}: {value}" for key, value in args.items()]
    return " · ".join(parts)


def _auftrag(run_id: str) -> str:
    """Der Auftrag, der zu dieser Freigabe gehört (Text des Nutzers am Lauf)."""
    if not run_id:
        return ""
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        zeile = conn.execute(
            "SELECT run_data FROM ai.agno_runs WHERE run_id = %s", (run_id,)
        ).fetchone()
    finally:
        conn.close()
    if zeile is None:
        return ""
    daten = (zeile["run_data"] or {}).get("input") or {}
    text = str(daten.get("input_content") or "").strip()
    if not text:
        return ""
    text = text.replace("&", "&amp;").replace("<", "&lt;")
    return f'<p style="margin:0.25rem 0"><em>Auftrag:</em> {text[:400]}</p>'


def _entwurf(user_id: str, draft_id: str) -> str:
    """Empfänger, Betreff und Anfang des Entwurfs; leer, wenn er nicht mehr existiert."""
    if not draft_id:
        return ""
    try:
        from officeassistant.agents.session import resolve_session

        conn = db.connect(SETTINGS.db_url, autocommit=True)
        try:
            session = resolve_session(conn, user_id, "send_draft", SETTINGS.token_key)
        finally:
            conn.close()
        nachricht = session.provider.get_message(draft_id)
    except Exception as fehler:  # noqa: BLE001 - Anzeige statt Absturz
        return (
            '<p style="margin:0.25rem 0;color:#8a1f11">'
            f"Der Entwurf {draft_id} ist im Postfach nicht (mehr) vorhanden. "
            f"Grund: {type(fehler).__name__}</p>"
        )

    text = nachricht.body_text.replace("&", "&amp;").replace("<", "&lt;")[:400]
    return f"""
    <p style="margin:0.25rem 0"><em>An:</em> {', '.join(nachricht.to) or '—'}<br>
       <em>Betreff:</em> {nachricht.header.subject or '—'}</p>
    <pre style="white-space:pre-wrap;margin:0.25rem 0;font-family:inherit">{text}</pre>
    """


def _render(rows: list[dict], message: str = "", user_id: str = "") -> None:
    if message:
        layout.banner(message)
    if not rows:
        layout.card("Offene Freigaben", "<p>Es liegt nichts zur Entscheidung vor.</p>")
        return
    items = "".join(
        f"""
        <div style="border-top:1px solid #d0d0d0;padding:0.75rem 0">
          <p><strong>{TOOLS.get(row.get('tool_name', ''), row.get('tool_name', ''))}</strong>
             — {STATUS.get(row.get('status', ''), row.get('status', ''))}</p>
          <p>{_arguments(row.get('tool_args') or {})}</p>
          {_auftrag(str(row.get('run_id', '')))}
          {_entwurf(user_id, str((row.get('tool_args') or {}).get('draft_id', '')))}
          <form method="post" action="/freigaben/{row['id']}" style="display:flex;gap:0.5rem">
            <input type="hidden" name="entscheidung" value="">
            <kol-button _label="Freigeben" _variant="primary" data-feld="entscheidung" data-wert="approved"></kol-button>
            <kol-button _label="Ablehnen" _variant="secondary" data-feld="entscheidung" data-wert="rejected"></kol-button>
          </form>
        </div>
        """
        for row in rows
    )
    layout.card("Offene Freigaben", items)


@ui.page("/freigaben")
async def approvals_page(request: Request) -> None:
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
        layout.app_frame("Freigaben", user.name or user.email)
        layout.nav("/freigaben")
        _body(request, user)


def _body(request: Request, user) -> None:
    try:
        rows = API.approvals(user.access_token)
    except Exception as exc:  # noqa: BLE001 - Anzeige statt Absturz
        _render([], f"Freigaben konnten nicht geladen werden: {exc}", user.subject)
        return

    message = request.query_params.get("meldung", "")
    _render(rows, message, user.subject)


async def decide(request: Request):
    """Formularentscheidung: prüfen, auflösen, Lauf fortsetzen."""
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    try:
        token = await auth.access_token(request, SETTINGS)
    except auth.NotAuthenticated:
        return RedirectResponse("/login", status_code=303)
    user = auth.with_fresh_token(user, token)

    form = await request.form()
    approval_id = request.path_params["approval_id"]
    decision = str(form.get("entscheidung", ""))
    if decision not in ("approved", "rejected"):
        return RedirectResponse("/freigaben?meldung=Unbekannte+Entscheidung", status_code=303)

    try:
        resolved = API.resolve(token, approval_id, decision, user.email or user.subject)
        note = "Freigegeben." if decision == "approved" else "Abgelehnt."
        if decision == "approved" and resolved.get("run_id"):
            # Der Lauf arbeitet danach Minuten weiter. Würde die Seite darauf warten,
            # bricht die Verbindung ab und der Nutzer sieht „connection lost", obwohl die
            # Aktion ausgeführt wurde. Deshalb läuft die Fortsetzung im Hintergrund.
            asyncio.create_task(
                _fortsetzen(
                    token,
                    str(resolved["run_id"]),
                    str(resolved.get("session_id", "")),
                )
            )
            note = "Freigegeben. Der Lauf arbeitet im Hintergrund weiter."
    except NotYours:
        note = "Diese Freigabe gehört nicht zu Ihrem Konto."
    except NoApprover as exc:
        note = str(exc)
    except Exception as exc:  # noqa: BLE001 - Meldung statt Absturz
        note = f"Auflösung fehlgeschlagen: {exc}"

    return RedirectResponse(f"/freigaben?meldung={quote(note)}", status_code=303)


async def _fortsetzen(token: str, run_id: str, session_id: str) -> None:
    """Lauf im Hintergrund fortsetzen; Fehler landen im Lauf, nicht in der Oberfläche."""
    try:
        await asyncio.to_thread(
            API.continue_run, token, run_id, session_id, SETTINGS.agent_id
        )
    except Exception:  # noqa: BLE001 - der Lauf zeigt seinen Stand selbst
        return


def register(app) -> None:
    app.add_route(
        "/freigaben/{approval_id}", decide, methods=["POST"], name="approval_decide"
    )
