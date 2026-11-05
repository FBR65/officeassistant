"""Ausführung einer Routine (P4.2 bis P4.4).

Der Lauf baut einen eigenen Agenten, weil er ohne angemeldeten Menschen startet. Er liest
und formuliert; er sendet nie. Das Ergebnis steht in `routine_run` und ist damit in der
Oberfläche sichtbar.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agno.agent import Agent

from officeassistant.agents.mail_tools import MAIL_TOOLS, configure_session
from officeassistant.agents.session import SessionResolver
from officeassistant.routines.store import (
    Routine,
    _routine,
    finish_run,
    start_run,
)
from officeassistant.settings import Settings
from officeassistant.store import db

TOOLS = {tool.name: tool for tool in MAIL_TOOLS}

LESEN = [TOOLS["search_mail"], TOOLS["read_mail"]]
MIT_KALENDER = [TOOLS["list_calendar"], *LESEN]
MIT_KENNZEICHEN = [*LESEN, TOOLS["label_mail"], TOOLS["archive_mail"]]
MIT_ENTWURF = [*LESEN, TOOLS["create_draft"]]

# Befugnis der Routine → Werkzeuge. `send_draft` steht in keiner Zeile.
WERKZEUGE = {
    "read": MIT_KALENDER,
    "label": MIT_KENNZEICHEN,
    "draft": MIT_ENTWURF,
}

# Was eine Routine tut, in einfacher Sprache. Der Text im Datensatz ergänzt ihn.
VORGABEN = {
    "morgenbriefing": (
        "Erstelle das Morgenbriefing für heute. Arbeite in dieser Reihenfolge: "
        "1) list_calendar für heute aufrufen. 2) search_mail ohne Suchbegriff aufrufen, "
        "um die neuesten Nachrichten zu sehen; lies die wichtigsten mit read_mail. "
        "3) Berichte Termine mit Uhrzeit, Nachrichten mit Entscheidungsbedarf und offene "
        "Aufgaben. Halte dich kurz und nutze Aufzählungen. Fehlt eine Auskunft, nenne den "
        "Grund aus der Antwort des Werkzeugs.",
        MIT_KALENDER,
    ),
    "inbox-triage": (
        "Ordne den Posteingang. Rufe zuerst search_mail ohne Suchbegriff auf. Lies dann "
        "höchstens acht Nachrichten mit read_mail. Nenne je gelesener Nachricht eine "
        "Zeile mit Absender, Betreff und einer Einordnung (dringend, zur Kenntnis, "
        "Werbung, Aufgabe mit Frist). Kennzeichne nur, wenn der Auftrag es ausdrücklich "
        "verlangt.",
        MIT_KENNZEICHEN,
    ),
    "meeting-vorbereitung": (
        "Bereite die Termine der nächsten zwei Stunden vor: je Termin eine kurze Notiz "
        "mit Teilnehmern, Thema und den letzten Nachrichten der Teilnehmer. Ohne Termine "
        "antworte: „Heute keine Termine.“",
        MIT_KALENDER,
    ),
}


def _prompt(routine: Routine) -> str:
    vorgabe, _ = VORGABEN.get(routine.name, ("", LESEN))
    teile = [routine.prompt.strip(), vorgabe]
    return "\n\n".join(teil for teil in teile if teil)


def _tools(routine: Routine):
    """Die Werkzeuge folgen der gespeicherten Befugnis, nicht dem Namen.

    Die drei mitgelieferten Routinen haben feste Vorgaben; eine eigene Routine bekommt,
    was der Nutzer gewählt hat.
    """
    if routine.name in VORGABEN:
        return VORGABEN[routine.name][1]
    return WERKZEUGE.get(routine.scope, LESEN)


def build_routine_agent(settings: Settings, routine: Routine) -> Agent:
    """Eigener Agent je Lauf; die Werkzeuge folgen dem Zweck der Routine."""
    from agno.models.openai.like import OpenAILike

    return Agent(
        id=f"routine-{routine.name}",
        name=routine.name,
        model=OpenAILike(
            id=settings.role_leader,
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
        ),
        tools=_tools(routine),
        instructions=[
            "Du arbeitest ohne Rückfrage im Hintergrund.",
            "Antworte auf Deutsch, sachlich, in der Sie-Form.",
            "Erfinde nichts. Kannst du etwas nicht lesen, sage es mit dem Grund.",
            "Sende nichts. Senden darf nur ein Mensch nach ausdrücklicher Freigabe.",
            "Dir stehen nur die Werkzeuge zur Verfügung, die dir übergeben wurden. "
            "Fehlt eines, sage das, statt eine andere Lösung zu behaupten.",
        ],
        markdown=True,
    )


def run_routine(routine: Routine, settings: Settings | None = None) -> dict:
    """Routine ausführen und Ergebnis ablegen. Gibt Kennung, Stand und Text zurück."""
    settings = settings or Settings.load()
    configure_session(SessionResolver(db_url=settings.db_url, token_key=settings.token_key))

    conn = db.connect(settings.db_url, autocommit=True)
    try:
        run_id = start_run(conn, routine)
        agent = build_routine_agent(settings, routine)
        try:
            antwort = agent.run(_prompt(routine), user_id=routine.user_id)
            text = str(getattr(antwort, "content", "") or "")
            # Werkzeugnamen ins Protokoll: ohne sie ist nicht erkennbar, ob eine Auskunft
            # aus dem Postfach stammt oder erfunden wurde.
            gerufen = [
                str(getattr(werkzeug, "tool_name", "") or getattr(werkzeug, "name", ""))
                for werkzeug in (getattr(antwort, "tools", None) or [])
            ]
            print(f"Routine {routine.name}: Werkzeuge {gerufen or 'keine'}")
            finish_run(conn, run_id, "completed", output=text)
            return {"run_id": run_id, "status": "completed", "output": text}
        except Exception as exc:  # noqa: BLE001 - Lauf scheitert, Nutzer sieht den Grund
            grund = f"{type(exc).__name__}: {exc}"
            finish_run(conn, run_id, "failed", error=grund)
            return {"run_id": run_id, "status": "failed", "error": grund}
    finally:
        conn.close()


def due_routines(conn, jetzt: datetime | None = None) -> list[Routine]:
    """Alle aktiven Routinen, deren Zeitplan in dieser Minute fällig ist."""
    from officeassistant.routines.store import is_due

    jetzt = jetzt or datetime.now(UTC)
    rows = conn.execute(
        """
        SELECT r.id, r.user_id, r.name, r.cron, r.prompt, r.trust, r.enabled
        FROM routine r JOIN app_user u ON u.id = r.user_id
        WHERE r.enabled AND u.active
        """
    ).fetchall()
    alle = [_routine(row) for row in rows]
    return [routine for routine in alle if is_due(routine, jetzt)]
