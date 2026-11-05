"""Tests der Freigabe-Auflösung über das Dienstkonto (Variante B)."""

from __future__ import annotations

import httpx
import pytest

from officeassistant.ui import agentapi
from officeassistant.ui.agentapi import AgentApi, NoApprover, NotYours


def _mock(monkeypatch, handler):
    original = httpx.get
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    def get(url, **kwargs):
        return client.get(url, **kwargs)

    def post(url, **kwargs):
        return client.post(url, **kwargs)

    monkeypatch.setattr(agentapi.httpx, "get", get)
    monkeypatch.setattr(agentapi.httpx, "post", post)
    return original


APPROVAL = {
    "id": "a1",
    "user_id": "alice-sub",
    "tool_name": "send_draft",
    "status": "pending",
}


def test_foreign_approval_is_rejected_before_any_write(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404, json={"detail": "Approval not found"})

    _mock(monkeypatch, handler)
    api = AgentApi(base_url="http://api", approver_token="pat")

    with pytest.raises(NotYours):
        api.resolve("member-token", "a1", "approved", "alice@example.org")

    assert all("/resolve" not in url for url in calls)


def test_resolve_uses_the_service_account_and_records_the_human(monkeypatch):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=APPROVAL)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={**APPROVAL, "status": "approved"})

    _mock(monkeypatch, handler)
    api = AgentApi(base_url="http://api", approver_token="pat-service")

    result = api.resolve("member-token", "a1", "approved", "alice@example.org")

    assert result["status"] == "approved"
    assert seen["auth"] == "Bearer pat-service"
    assert "alice@example.org" in str(seen["body"])
    assert "entschieden_von" in str(seen["body"])


def test_resolve_without_service_account_fails_in_german():
    api = AgentApi(base_url="http://api", approver_token="")

    with pytest.raises(NoApprover) as err:
        api.resolve("member-token", "a1", "approved", "alice@example.org")

    assert "OA_APPROVER_TOKEN" in str(err.value)


def test_continue_needs_the_session_id(monkeypatch):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"status": "COMPLETED"})

    _mock(monkeypatch, handler)
    api = AgentApi(base_url="http://api")

    api.continue_run("member-token", "run-1", "session-1", "office-assistant")

    assert "session_id=session-1" in seen["body"]
