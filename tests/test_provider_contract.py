from __future__ import annotations

from datetime import UTC, datetime, timedelta

from officeassistant.providers.base import MailProvider
from officeassistant.providers.text import html_to_text
from tests.fakes import FakeProvider


def test_fake_provider_satisfies_the_contract():
    assert isinstance(FakeProvider(), MailProvider)


def test_a_partial_implementation_is_rejected():
    class Broken:
        @property
        def address(self) -> str:
            return "x@example.org"

        def list_folders(self) -> list[str]:
            return []

    assert not isinstance(Broken(), MailProvider)


def test_search_returns_newest_first_and_respects_the_limit():
    provider = FakeProvider()
    provider.seed(count=5)

    headers = provider.search("", limit=3)

    assert len(headers) == 3
    assert headers[0].received_at >= headers[-1].received_at


def test_search_respects_since():
    provider = FakeProvider()
    provider.seed(count=4)

    cutoff = datetime.now(UTC) - timedelta(hours=1, minutes=30)
    headers = provider.search("", since=cutoff)

    assert all(header.received_at >= cutoff for header in headers)


def test_draft_and_send_produce_a_sent_message():
    provider = FakeProvider()

    draft = provider.create_draft(("ziel@example.org",), "Hallo", "Text")
    result = provider.send_draft(draft.provider_id)

    assert result.provider_id in provider.messages
    assert provider.messages[result.provider_id].header.labels == ("SENT",)
    assert [name for name, *_ in provider.calls][-2:] == ["create_draft", "send_draft"]


def test_html_becomes_readable_text():
    html = (
        "<html><head><style>p{color:red}</style></head>"
        "<body><p>Guten&nbsp;Tag</p><p>Zweite Zeile<br>dritte</p>"
        "<script>alert(1)</script></body></html>"
    )

    text = html_to_text(html)

    assert "Guten Tag" in text
    assert "Zweite Zeile" in text
    assert "dritte" in text
    assert "<" not in text
    assert "alert" not in text
    assert "color:red" not in text
