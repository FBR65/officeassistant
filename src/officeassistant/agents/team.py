"""Das Team aus P4.1: Leitung plus vier Fachrollen.

Die Leitung bekommt den Auftrag, entscheidet selbst nichts Fachliches und reicht an die
Rolle weiter, die zuständig ist. Jede Rolle sieht nur die Werkzeuge, die zu ihr gehören:
Triage darf kennzeichnen, aber nicht senden; Entwurf darf schreiben, aber nicht senden;
Termine dürfen lesen; Recherche hat eigene Werkzeuge erst mit der Wissensbasis (P4.7).
"""

from __future__ import annotations

from agno.agent import Agent
from agno.team import Team
from agno.team.mode import TeamMode

from officeassistant.agents.mail_tools import MAIL_TOOLS

TOOLS = {tool.name: tool for tool in MAIL_TOOLS}

LESEN = [TOOLS["search_mail"], TOOLS["read_mail"]]
TRIAGE = [*LESEN, TOOLS["label_mail"], TOOLS["archive_mail"]]
ENTWURF = [*LESEN, TOOLS["create_draft"]]
TERMINE = [TOOLS["list_calendar"], *LESEN]

DEUTSCH = [
    "Antworte auf Deutsch, sachlich und in der Sie-Form.",
    "Erfinde keine Nachricht, keinen Termin und keine Kennung.",
    "Sage klar, wenn eine Auskunft nicht möglich ist, und nenne den Grund.",
]

NICHT_SENDEN = (
    "Sende nichts. Senden darf nur ein Mensch nach ausdrücklicher Freigabe."
)


def build_members(model) -> list[Agent]:
    """Vier Rollen; `model` ist eine Fabrik, damit jede Rolle ihr eigenes Modell bekommt."""
    triage = Agent(
        id="triage",
        name="Posteingang",
        role="Sortiert den Posteingang und kennzeichnet Nachrichten.",
        model=model(),
        tools=TRIAGE,
        instructions=[
            *DEUTSCH,
            "Du ordnest eingehende Nachrichten: dringend, zur Kenntnis, Werbung, "
            "Aufgabe mit Frist.",
            "Kennzeichne nur, was der Auftrag verlangt; lösche nichts endgültig.",
            NICHT_SENDEN,
        ],
    )
    entwurf = Agent(
        id="entwurf",
        name="Entwurf",
        role="Schreibt Antwortentwürfe.",
        model=model(),
        tools=ENTWURF,
        instructions=[
            *DEUTSCH,
            "Du schreibst Entwürfe mit create_draft. Das Senden übernimmt ein Mensch.",
            "Halte Entwürfe kurz, höflich und ohne Floskeln.",
            NICHT_SENDEN,
        ],
    )
    termine = Agent(
        id="termine",
        name="Termine",
        role="Liest den Kalender und bereitet Termine vor.",
        model=model(),
        tools=TERMINE,
        instructions=[
            *DEUTSCH,
            "Du beantwortest Fragen zu Terminen aus list_calendar.",
            "Kann der Anbieter keinen Kalender (IMAP), sage das mit dem Hinweis auf "
            "Exchange Online über Microsoft Graph.",
            NICHT_SENDEN,
        ],
    )
    recherche = Agent(
        id="recherche",
        name="Recherche",
        role="Sucht Belege im Postfach zusammen.",
        model=model(),
        tools=LESEN,
        instructions=[
            *DEUTSCH,
            "Du suchst Nachrichten und führst Fundstellen mit Betreff, Absender und "
            "Datum zusammen.",
            NICHT_SENDEN,
        ],
    )
    return [triage, entwurf, termine, recherche]


def build_team(model) -> Team:
    """Leitung mit klarer Zuständigkeit; sie führt selbst keine Fachaufgabe aus."""
    return Team(
        id="office-team",
        name="Office-Team",
        role="Nimmt Aufträge an und reicht sie an die zuständige Rolle weiter.",
        model=model(),
        members=build_members(model),  # type: ignore[arg-type]
        mode=TeamMode.route,
        instructions=[
            *DEUTSCH,
            "Du verteilst Aufträge. Führe keine Fachaufgabe selbst aus.",
            "Posteingang ordnen oder kennzeichnen → Posteingang.",
            "Antwort schreiben oder Entwurf → Entwurf.",
            "Termine, Kalender, Verfügbarkeit → Termine.",
            "Suchen, zusammenfassen, belegen → Recherche.",
            "Fasse die Antwort der Rolle für den Menschen zusammen und nenne die Rolle, "
            "die geantwortet hat.",
            NICHT_SENDEN,
        ],
    )
