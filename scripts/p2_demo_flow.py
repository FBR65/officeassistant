"""P2-Ablauf als Skript: Lauf starten, Freigabe über das Dienstkonto auflösen, fortsetzen.

Zeigt Variante B ohne Browser: der Mensch entscheidet, das Dienstkonto führt aus.

Aufruf:
  OA_APPROVER_TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/approver_token.json'))['token'])") \
  uv run python scripts/p2_demo_flow.py
"""

from __future__ import annotations

import json
import os
import sys

import httpx

from officeassistant.settings import Settings
from officeassistant.ui.agentapi import AgentApi

KC_TOKEN = "http://127.0.0.1:8180/realms/oa/protocol/openid-connect/token"


def member_token() -> str:
    response = httpx.post(
        KC_TOKEN,
        data={
            "grant_type": "password",
            "client_id": "oa-ui-member",
            "client_secret": "membersecret",
            "username": "alice",
            "password": "alicepw",
            "scope": "openid",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> int:
    settings = Settings.load()
    api = AgentApi(
        base_url=settings.api_base_url,
        approver_token=os.environ.get("OA_APPROVER_TOKEN", ""),
    )
    token = member_token()

    run = httpx.post(
        f"{settings.api_base_url}/agents/{settings.agent_id}/runs",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "message": "Antworte auf Testnachricht 0 mit: Danke, erhalten. Sende die Mail ab.",
            "stream": "false",
        },
        timeout=300,
    )
    run.raise_for_status()
    body = run.json()
    print("1) Lauf:", body.get("status"))
    print("   Werkzeuge:", [t.get("tool_name") for t in body.get("tools", [])])

    pending = api.approvals(token)
    if not pending:
        print("Keine offene Freigabe — Abbruch.")
        return 1
    approval = pending[0]
    print("2) Offen:", approval["tool_name"], approval["tool_args"])

    resolved = api.resolve(token, approval["id"], "approved", "alice@example.org")
    print("3) Auflösung:", resolved.get("status"), "| resolved_by:", resolved.get("resolved_by"))

    continued = api.continue_run(
        token, str(approval["run_id"]), str(approval.get("session_id", "")), settings.agent_id
    )
    print("4) Fortsetzung:", continued.get("status"))
    print("   Antwort:", str(continued.get("content"))[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
