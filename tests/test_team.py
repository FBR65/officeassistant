"""Aufbau des Teams (P4.1): Rollen, Werkzeuge und die Sperre gegen Senden.

Die Prüfung braucht kein Netz: Modelle werden nur erzeugt, nicht aufgerufen.
"""

from __future__ import annotations

from agno.models.openai.like import OpenAILike

from officeassistant.agents.team import build_team


def _mitglieder(team) -> list:
    """Agno erlaubt eine Liste oder eine Funktion; hier ist es immer eine Liste."""
    return list(team.members)  # type: ignore[arg-type]


def _anweisungen(wert) -> str:
    if isinstance(wert, str):
        return wert
    return " ".join(wert or [])


def _model() -> OpenAILike:
    return OpenAILike(id="testmodell", base_url="http://127.0.0.1:1/v1", api_key="x")


def test_team_has_the_four_roles():
    team = build_team(_model)

    ids = [member.id for member in _mitglieder(team)]
    assert ids == ["triage", "entwurf", "termine", "recherche"]


def test_no_role_may_send():
    team = build_team(_model)

    for member in _mitglieder(team):
        namen = {tool.name for tool in (member.tools or [])}
        assert "send_draft" not in namen, f"{member.id} darf nicht senden"


def test_roles_only_see_their_own_tools():
    team = build_team(_model)
    rollen = {
        member.id: {tool.name for tool in (member.tools or [])} for member in _mitglieder(team)
    }

    assert {"label_mail", "archive_mail"} <= rollen["triage"]
    assert rollen["entwurf"] == {"search_mail", "read_mail", "create_draft"}
    assert rollen["termine"] == {"list_calendar", "search_mail", "read_mail"}
    assert rollen["recherche"] == {"search_mail", "read_mail"}


def test_instructions_are_german_and_forbid_sending():
    team = build_team(_model)

    leitung = _anweisungen(team.instructions)
    assert "Deutsch" in leitung
    assert "Freigabe" in leitung or "Sende nichts" in leitung

    for member in _mitglieder(team):
        text = _anweisungen(member.instructions)
        assert "Deutsch" in text, member.id
        assert "Sende nichts" in text, member.id


def test_the_leader_routes_instead_of_working():
    team = build_team(_model)

    leitung = _anweisungen(team.instructions)
    for rolle in ("Posteingang", "Entwurf", "Termine", "Recherche"):
        assert rolle in leitung
    assert "Führe keine Fachaufgabe selbst aus" in leitung
