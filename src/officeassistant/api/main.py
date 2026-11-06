"""AgentOS-Backend (P1.8): Agenten hinter JWT-Prüfung und Nutzertrennung.

Start: uv run uvicorn officeassistant.api.main:app --port 7777
Voraussetzung: OA_* gesetzt, JWT_JWKS_FILE zeigt auf die JWKS-Datei des Ausstellers.
"""

from __future__ import annotations

import os
from pathlib import Path

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai.like import OpenAILike
from agno.os import AgentOS
from agno.os.authz import Authorization

from officeassistant.agents.mail_tools import MAIL_TOOLS, configure_session
from officeassistant.agents.document_tools import DOCUMENT_TOOLS
from officeassistant.agents.presentation_tools import PRESENTATION_TOOLS
from officeassistant.agents.connector_tools import CONNECTOR_TOOLS
from officeassistant.agents.memory_tools import MEMORY_TOOLS, memory_instructions
from officeassistant.agents.session import SessionResolver
from officeassistant.agents.team import build_team
from officeassistant.settings import Settings

SETTINGS = Settings.load()
JWKS_FILE = Path(os.environ.get("JWT_JWKS_FILE", ""))

configure_session(SessionResolver(db_url=SETTINGS.db_url, token_key=SETTINGS.token_key))


def _check_jwks() -> None:
    """Ohne ladbaren Schlüssel startet AgentOS nicht — dann lieber gleich mit klarer Meldung."""
    if not os.environ.get("JWT_JWKS_FILE"):
        raise RuntimeError(
            "JWT_JWKS_FILE fehlt. Die Datei mit den Schlüsseln des Ausstellers "
            "(Keycloak: /realms/<realm>/protocol/openid-connect/certs) muss gesetzt sein."
        )
    if not JWKS_FILE.is_file():
        raise RuntimeError(f"JWT_JWKS_FILE zeigt auf keine Datei: {JWKS_FILE}")


def _model(role_id: str) -> OpenAILike:
    return OpenAILike(
        id=role_id,
        base_url=SETTINGS.model_base_url,
        api_key=SETTINGS.model_api_key,
    )


def build_app():
    _check_jwks()
    db = PostgresDb(db_url=SETTINGS.db_url.replace("postgresql://", "postgresql+psycopg://"))

    basis = [
        "Du bist ein deutschsprachiger Büroassistent.",
        "Antworte knapp, sachlich und in der Sie-Form.",
        "Nutze search_mail und read_mail, bevor du etwas über Mails behauptest.",
        "Führe keine Schreibaktion ohne Freigabe aus.",
        "Wenn der Nutzer Sie korrigiert, merke die Lehre mit remember.",
        "Für eine Übersicht genügt der Anriss aus search_mail; lies höchstens fünf Nachrichten "
        "im Volltext.",
        "create_presentation: Steht im Ergebnis \"erstellt\": true, ist die Datei abgelegt; "
        "rufe das Werkzeug dann nicht erneut auf.",
        "Baust du eine Präsentation aus hochgeladenen Dokumenten, gib bei create_presentation "
        "die Nummern als quelle_dokumente an. Dann wird jede Folie gegen den "
        "Text geprüft.",
        "Steht im Ergebnis ein Feld \"fehler\", ist NICHTS entstanden. Nenne den Fehler wörtlich "
        "und behaupte keinen Erfolg.",
        "Lehnt create_presentation Begriffe als nicht belegt ab, übernimm beim zweiten Versuch "
        "den Wortlaut aus dem Dokument, statt neu zu formulieren. Nach zwei Ablehnungen höre "
        "auf und nenne die strittigen Begriffe.",
        "Nutze nur Werkzeuge, die der Auftrag verlangt. list_calendar ausschließlich bei "
        "Fragen nach Terminen, sonst nie.",
        'Liefert ein Werkzeug ein Feld "fehler", gib diesen Text wieder, statt eine eigene '
        "Erklärung zu erfinden.",
    ]

    def anweisungen(run_context=None) -> list[str]:
        """Grundregeln plus die Merksätze dieses Nutzers (P4.7)."""
        return [*basis, *memory_instructions(run_context)]

    assistant = Agent(
        id="office-assistant",
        name="OfficeAssistant",
        model=_model(SETTINGS.role_leader),
        tools=[*MAIL_TOOLS, *MEMORY_TOOLS, *CONNECTOR_TOOLS, *PRESENTATION_TOOLS, *DOCUMENT_TOOLS],
        instructions=anweisungen,
        db=db,
        # Verlauf klein halten: Werkzeugergebnisse früherer Läufe (Postfachlisten,
        # Nachrichtentexte) würden sonst bei jeder neuen Anfrage erneut mitgeschickt und
        # das Kontextfenster sprengen.
        # Jeder Auftrag steht für sich: der Verlauf früherer Läufe enthält Postfachlisten und
        # Nachrichtentexte und sprengt sonst das Kontextfenster des lokalen Modells.
        # Ohne diese Grenze bricht Agno nach drei Werkzeugaufrufen ab („Tool count limit hit"),
        # und eine Übersicht über das Postfach käme nie zustande.
        tool_call_limit=20,
        add_history_to_context=False,
        num_history_runs=0,
        max_tool_calls_from_history=0,
        compress_tool_results=True,
    )

    team = build_team(lambda: _model(SETTINGS.role_leader))

    agent_os = AgentOS(
        id="officeassistant",
        agents=[assistant],
        teams=[team],
        db=db,
        authorization=Authorization(jwks_file=str(JWKS_FILE), algorithm="RS256"),
        user_isolation=True,
    )
    return agent_os.get_app()


app = build_app()
