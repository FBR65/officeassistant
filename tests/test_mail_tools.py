"""Tests der Postfach-Werkzeuge (P2, Testanbieter)."""

from __future__ import annotations

import pytest
from agno.run.base import RunContext

from officeassistant.agents import mail_tools
from officeassistant.agents.mail_tools import (
    MAIL_TOOLS,
    MailSession,
    ToolDenied,
    archive_mail,
    create_draft,
    label_mail,
    read_mail,
    search_mail,
    send_draft,
)
from officeassistant.providers.fake import FakeProvider


def context(user_id: str | None = "alice", name: str = "alice") -> RunContext:
    return RunContext(run_id=f"run-{name}", session_id=f"session-{name}", user_id=user_id)


class FakeAudit:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def append(self, user_id, tool, args, result_code) -> None:
        self.rows.append((user_id, tool, args, result_code))


def session(trust: str = "approval-required", audit: FakeAudit | None = None) -> MailSession:
    return MailSession(
        user_id="alice",
        provider=FakeProvider(address="alice@example.org"),
        trust=trust,  # type: ignore[arg-type]
        audit=audit,
    )


@pytest.fixture()
def wired(monkeypatch):
    current = session()

    def resolver(_ctx):
        return current

    monkeypatch.setattr(mail_tools, "_resolve", resolver)
    return current


def test_search_returns_german_header_fields(wired):
    rows = search_mail.entrypoint("", run_context=context())

    assert rows
    assert {"id", "betreff", "von", "datum"} <= set(rows[0])
    assert rows[0]["betreff"].startswith("Testnachricht")


def test_read_returns_plain_text(wired):
    header = wired.provider.search("", limit=1)[0]

    message = read_mail.entrypoint(header.provider_id, run_context=context())

    assert message["text"] == "Inhalt 0"
    assert "<" not in message["text"]


def test_create_draft_does_not_send(wired):
    draft = create_draft.entrypoint(
        ["ziel@example.org"], "Hallo", "Text", run_context=context()
    )

    assert draft["betreff"] == "Hallo"
    assert wired.provider.sent == []


def test_read_only_blocks_label(wired, monkeypatch):
    monkeypatch.setattr(mail_tools, "_resolve", lambda _ctx: session(trust="read-only"))
    header = wired.provider.search("", limit=1)[0]

    with pytest.raises(ToolDenied) as err:
        label_mail.entrypoint(header.provider_id, "Wichtig", run_context=context())

    assert "Lesen gestellt" in str(err.value)


def test_write_tools_require_confirmation():
    for tool in (send_draft, label_mail, archive_mail):
        assert tool.requires_confirmation is True
        assert tool.approval_type == "required"


def test_read_tools_do_not_require_confirmation():
    for tool in (search_mail, read_mail, create_draft):
        assert not tool.requires_confirmation


def test_audit_row_is_written(wired, monkeypatch):
    audit = FakeAudit()
    monkeypatch.setattr(mail_tools, "_resolve", lambda _ctx: session(audit=audit))
    header = wired.provider.search("", limit=1)[0]

    archive_mail.entrypoint(header.provider_id, run_context=context())

    assert audit.rows == [
        ("alice", "archive_mail", None, "called"),
        ("alice", "archive_mail", {"id": header.provider_id}, "archived"),
    ]


def test_all_tools_are_registered():
    names = {tool.name for tool in MAIL_TOOLS}
    assert names == {
        "search_mail",
        "read_mail",
        "list_calendar",
        "create_draft",
        "send_draft",
        "label_mail",
        "archive_mail",
    }


def test_missing_user_is_rejected(wired):
    with pytest.raises(ToolDenied):
        search_mail.entrypoint("", run_context=context(user_id=None))


def test_unknown_message_id_returns_a_hint_instead_of_crashing(wired):
    result = read_mail.entrypoint("0", run_context=context())

    assert "fehler" in result
    assert "search_mail" in result["fehler"]


def test_unknown_draft_id_is_reported(wired):
    message = send_draft.entrypoint("d99", run_context=context())

    assert "Unbekannter Entwurf" in message


def test_read_mail_shortens_long_bodies():
    """Lange Körper sprengen das Kontextfenster; der Anfang genügt."""
    from officeassistant.agents import mail_tools

    lang = "Zeile\n" * 3000

    class Provider:
        address = "a@example.org"

        def get_message(self, message_id):
            from datetime import UTC, datetime

            from officeassistant.providers.base import Message, MessageHeader

            return Message(
                header=MessageHeader(
                    provider_id=message_id,
                    thread_id="t",
                    sender="b@example.org",
                    subject="Lang",
                    received_at=datetime.now(UTC),
                ),
                body_text=lang,
            )

    session = mail_tools.MailSession(
        user_id="u", provider=Provider(), trust="read-only", audit=None
    )
    mail_tools.configure_session(lambda _context: session)

    ergebnis = mail_tools.read_mail.entrypoint("m1", run_context=context())

    assert ergebnis["gekuerzt"] is True
    assert len(ergebnis["text"]) == mail_tools.MAX_TEXT
