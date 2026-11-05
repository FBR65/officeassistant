"""Prüfskript: Ruft ein Routine-Werkzeug auf und zeigt, was zurückkommt.

Dient dazu, erfundene Auskünfte von echten Werkzeugantworten zu unterscheiden.
"""

from __future__ import annotations

import sys

from agno.run import RunContext

from officeassistant.agents.mail_tools import MAIL_TOOLS, configure_session
from officeassistant.agents.session import SessionResolver
from officeassistant.settings import Settings


def main() -> None:
    settings = Settings.load()
    configure_session(SessionResolver(db_url=settings.db_url, token_key=settings.token_key))

    user_id = sys.argv[1] if len(sys.argv) > 1 else "ae643b35-86f3-4745-9af8-7bb78b9fb3e9"
    werkzeug = {tool.name: tool for tool in MAIL_TOOLS}

    kontext = RunContext(run_id="probe", session_id="probe", user_id=user_id)

    for name in ("list_calendar", "search_mail"):
        tool = werkzeug[name]
        try:
            if name == "list_calendar":
                ergebnis = tool.entrypoint(run_context=kontext)
            else:
                ergebnis = tool.entrypoint("", run_context=kontext)
            print(f"{name}: {str(ergebnis)[:400]}")
        except Exception as exc:  # noqa: BLE001 - Prüfskript zeigt den Fehler
            print(f"{name}: FEHLER {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
