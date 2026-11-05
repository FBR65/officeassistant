"""Seite „Aktivität": Läufe, Werkzeuge und Protokoll je Nutzer (P4.8).

Zwei Quellen: die Läufe aus AgentOS (`ai.agno_runs`) und das eigene Protokoll (`audit`).
Beide werden über die Nutzerkennung gefiltert; niemand sieht fremde Zeilen.
"""

from __future__ import annotations

from typing import Any, cast

from nicegui import ui
from starlette.requests import Request

from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()

STATUS = {
    "COMPLETED": "fertig",
    "RUNNING": "läuft",
    "PAUSED": "wartet auf Freigabe",
    "ERROR": "gescheitert",
    "failed": "gescheitert",
}


def _laeufe(user_id: str, grenze: int = 15) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        rows = conn.execute(
            """
            SELECT run_id, agent_id, team_id, status, created_at, run_data
            FROM ai.agno_runs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, grenze),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "<p>Noch kein Lauf.</p>"

    zeilen = []
    for row in rows:
        daten = cast(dict[str, Any], row)
        werkzeuge = _werkzeuge(daten.get("run_data"))
        token = _token(daten.get("run_data"))
        zeilen.append(
            f"""
            <tr>
              <td style="padding:0.4rem 0.5rem 0.4rem 0;white-space:nowrap">
                {_zeit(daten.get('created_at'))}
              </td>
              <td style="padding:0.4rem 0.5rem">{daten.get('agent_id') or daten.get('team_id') or '—'}</td>
              <td style="padding:0.4rem 0.5rem">{STATUS.get(str(daten.get('status')), str(daten.get('status')))}</td>
              <td style="padding:0.4rem 0.5rem">{werkzeuge}</td>
              <td style="padding:0.4rem 0;white-space:nowrap;text-align:right">{token}</td>
            </tr>
            """
        )

    return f"""
    <table style="width:100%;border-collapse:collapse;table-layout:fixed">
      <colgroup>
        <col style="width:9rem"><col style="width:10rem"><col style="width:8rem">
        <col><col style="width:8rem">
      </colgroup>
      <thead>
        <tr style="text-align:left;border-bottom:1px solid #d0d0d0">
          <th style="padding-bottom:0.5rem">Zeit</th>
          <th style="padding-bottom:0.5rem">Wer</th>
          <th style="padding-bottom:0.5rem">Stand</th>
          <th style="padding-bottom:0.5rem">Werkzeuge</th>
          <th style="padding-bottom:0.5rem;text-align:right">Token</th>
        </tr>
      </thead>
      <tbody>{''.join(zeilen)}</tbody>
    </table>
    """


def _werkzeuge(run_data: Any) -> str:
    """Werkzeugnamen aus den Laufdaten; leer heißt: das Modell hat keines benutzt."""
    if not isinstance(run_data, dict):
        return "—"
    roh = run_data.get("tools") or []
    namen = [
        str(eintrag.get("tool_name") or eintrag.get("name"))
        for eintrag in roh
        if isinstance(eintrag, dict)
    ]
    return ", ".join(namen) if namen else "keine"


def _token(run_data: Any) -> str:
    """Verbrauchte Token eines Laufs; ein Strich heißt: nicht gemeldet."""
    if not isinstance(run_data, dict):
        return "—"
    masse = run_data.get("metrics")
    if not isinstance(masse, dict):
        return "—"
    gesamt = masse.get("total_tokens")
    if gesamt is None:
        return "—"
    return f"{int(gesamt):,}".replace(",", ".")


def _zeit(wert: Any) -> str:
    if wert is None:
        return "—"
    from datetime import UTC, datetime

    return datetime.fromtimestamp(float(wert), UTC).astimezone().strftime("%d.%m. %H:%M")


def _protokoll(user_id: str, grenze: int = 15) -> str:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        rows = conn.execute(
            """
            SELECT tool, result_code, ts FROM audit
            WHERE user_id = %s ORDER BY ts DESC LIMIT %s
            """,
            (user_id, grenze),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "<p>Noch kein Werkzeugaufruf protokolliert.</p>"

    zeilen = "".join(
        f"""
        <tr>
          <td style="padding:0.35rem 0.5rem 0.35rem 0;white-space:nowrap">{row['ts']:%d.%m. %H:%M}</td>
          <td style="padding:0.35rem 0.5rem">{row['tool']}</td>
          <td style="padding:0.35rem 0">{row['result_code']}</td>
        </tr>
        """
        for row in (cast(dict[str, Any], eintrag) for eintrag in rows)
    )
    return f"""
    <table style="width:100%;border-collapse:collapse;table-layout:fixed">
      <colgroup><col style="width:10rem"><col style="width:14rem"><col></colgroup>
      <thead>
        <tr style="text-align:left;border-bottom:1px solid #d0d0d0">
          <th style="padding-bottom:0.5rem">Zeit</th>
          <th style="padding-bottom:0.5rem">Werkzeug</th>
          <th style="padding-bottom:0.5rem">Ergebnis</th>
        </tr>
      </thead>
      <tbody>{zeilen}</tbody>
    </table>
    """


@ui.page("/aktivitaet")
async def activity_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    with layout.content():
        layout.app_frame("Aktivität", user.name or user.email)
        layout.nav("/aktivitaet")
        layout.card("Läufe", _laeufe(user.subject))
        layout.card("Protokoll der Werkzeugaufrufe", _protokoll(user.subject))


def register(app) -> None:
    """Seite meldet sich über den Dekorator an."""
