"""Zugriff der Oberfläche auf die Agenten-API.

Freigaben löst ein Dienstkonto auf, weil Agno mit `user_isolation=True` nur
Administratoren auflösen lässt. Die Entscheidung trifft trotzdem der Mensch: die
Oberfläche prüft zuerst mit dem Token des Nutzers, dass die Freigabe ihm gehört, und
schickt erst dann das Dienstkonto los. Der Name des Menschen steht in `resolution_data`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class NotYours(RuntimeError):
    """Die Freigabe gehört einem anderen Nutzer (oder existiert nicht)."""


class NoApprover(RuntimeError):
    """Ohne Dienstkonto lässt sich keine Freigabe auflösen."""


@dataclass(slots=True)
class AgentApi:
    base_url: str
    approver_token: str = ""

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def approvals(self, member_token: str) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/approvals",
            params={"status": "pending"},
            headers=self._headers(member_token),
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def approval(self, member_token: str, approval_id: str) -> dict[str, Any]:
        """Freigabe lesen; fremde Freigaben melden sich als `NotYours`."""
        response = httpx.get(
            f"{self.base_url}/approvals/{approval_id}",
            headers=self._headers(member_token),
            timeout=15,
        )
        if response.status_code == 404:
            raise NotYours(f"Freigabe {approval_id} gehört nicht zu diesem Nutzer.")
        response.raise_for_status()
        return response.json()

    def resolve(
        self,
        member_token: str,
        approval_id: str,
        decision: str,
        human: str,
    ) -> dict[str, Any]:
        if decision not in ("approved", "rejected"):
            raise ValueError(f"Unbekannte Entscheidung: {decision}")
        if not self.approver_token:
            raise NoApprover(
                "Kein Dienstkonto für Freigaben gesetzt (OA_APPROVER_TOKEN fehlt). "
                "Ohne Dienstkonto kann Agno bei eingeschalteter Nutzertrennung nicht "
                "auflösen."
            )

        approval = self.approval(member_token, approval_id)
        response = httpx.post(
            f"{self.base_url}/approvals/{approval_id}/resolve",
            headers=self._headers(self.approver_token),
            json={
                "status": decision,
                "resolution_data": {
                    "entschieden_von": human,
                    "freigabe_von": approval.get("user_id", ""),
                    "werkzeug": approval.get("tool_name", ""),
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def continue_run(
        self, member_token: str, run_id: str, session_id: str, agent_id: str
    ) -> dict[str, Any]:
        """Angestoßenen Lauf fortsetzen. `session_id` ist Pflicht."""
        response = httpx.post(
            f"{self.base_url}/agents/{agent_id}/runs/{run_id}/continue",
            headers=self._headers(member_token),
            data={"session_id": session_id, "stream": "false"},
            timeout=300,
        )
        response.raise_for_status()
        return response.json()
