"""Prüfskript: Was liefert ein Anbindungs-Werkzeug wirklich zurück?"""

from __future__ import annotations

import sys

from agno.run import RunContext

from officeassistant.agents.connector_tools import CONNECTOR_TOOLS

WERKZEUGE = {werkzeug.name: werkzeug for werkzeug in CONNECTOR_TOOLS}


def main() -> None:
    user_id = sys.argv[1] if len(sys.argv) > 1 else "ae643b35-86f3-4745-9af8-7bb78b9fb3e9"
    kontext = RunContext(run_id="probe", session_id="probe", user_id=user_id)
    for name in ("search_jira", "search_confluence", "search_sharepoint", "search_onenote", "search_webex"):
        ergebnis = WERKZEUGE[name].entrypoint("Postfach", run_context=kontext)
        print(f"{name}: {ergebnis}")


if __name__ == "__main__":
    main()
