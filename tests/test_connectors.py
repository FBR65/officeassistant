"""Tests der Dienst-Anbindungen gegen Stubs (kein echter Dienst vorhanden).

Geprüft wird: Anfrage geht an den richtigen Pfad, mit dem richtigen Kopf, und das Ergebnis
wird sauber übersetzt. Ein echter Jira-, Confluence- oder Mattermost-Server stand nicht zur
Verfügung; das steht auch im Ergebnisdokument.
"""

from __future__ import annotations

import json

import httpx
import pytest

from officeassistant.connectors.atlassian import ConfluenceConnector, JiraConnector
from officeassistant.connectors.base import Connection, ConnectorError, NotConfigured
from officeassistant.connectors.mattermost import MattermostConnector
from officeassistant.connectors.microsoft import SharePointConnector, WebexConnector


def _verbindung(kind: str, base: str, **secret: str) -> Connection:
    return Connection(id=1, user_id="u", kind=kind, base_url=base, label="", secret=dict(secret))


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="https://stub.local", transport=httpx.MockTransport(handler))


def test_jira_search_builds_a_jql_and_reads_issues():
    gesehen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen["pfad"] = request.url.path
        gesehen["jql"] = request.url.params.get("jql")
        gesehen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "OA-12",
                        "fields": {
                            "summary": "Postfach verbinden",
                            "status": {"name": "In Arbeit"},
                            "assignee": {"displayName": "A. Beispiel"},
                        },
                    }
                ]
            },
        )

    verbindung = _verbindung("jira", "https://stub.local", email="a@example.org", token="t")
    treffer = JiraConnector(verbindung, client=_client(handler)).search("Postfach")

    assert gesehen["pfad"] == "/rest/api/3/search/jql"
    assert gesehen["jql"] == 'text ~ "Postfach"'
    assert gesehen["auth"].startswith("Basic ")
    assert treffer[0].key == "OA-12"
    assert treffer[0].status == "In Arbeit"


def test_jira_accepts_a_full_jql():
    gesehen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen["jql"] = request.url.params.get("jql")
        return httpx.Response(200, json={"issues": []})

    JiraConnector(
        _verbindung("jira", "https://stub.local", email="a@example.org", token="t"),
        client=_client(handler),
    ).search("project = OA AND status = Open")

    assert gesehen["jql"] == "project = OA AND status = Open"


def test_jira_error_is_reported_with_status_and_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(ConnectorError) as fehler:
        JiraConnector(
            _verbindung("jira", "https://stub.local", email="a@example.org", token="t"),
            client=_client(handler),
        ).search("x")

    assert "401" in str(fehler.value)


def test_jira_without_credentials_names_what_is_missing():
    with pytest.raises(ConnectorError) as fehler:
        JiraConnector(_verbindung("jira", "https://stub.local")).search("x")
    assert "API-Token" in str(fehler.value)


def test_confluence_search_returns_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/api/content/search"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "4711",
                        "title": "Betriebshandbuch",
                        "excerpt": "Wie der Dienst startet.",
                        "_links": {"webui": "/spaces/OA/pages/4711"},
                    }
                ]
            },
        )

    verbindung = _verbindung("confluence", "https://stub.local", email="a@example.org", token="t")
    seiten = ConfluenceConnector(verbindung, client=_client(handler)).search("Betrieb")

    assert seiten[0].title == "Betriebshandbuch"
    assert seiten[0].url == "/spaces/OA/pages/4711"


def test_mattermost_posts_into_the_given_channel():
    gesehen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen["pfad"] = request.url.path
        gesehen["koerper"] = json.loads(request.content)
        gesehen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(201, json={"id": "p1"})

    verbindung = _verbindung("mattermost", "https://stub.local", token="tok")
    MattermostConnector(verbindung, client=_client(handler)).post("Guten Morgen", "kanal-1")

    assert gesehen["pfad"] == "/api/v4/posts"
    assert gesehen["koerper"] == {"channel_id": "kanal-1", "message": "Guten Morgen"}
    assert gesehen["auth"] == "Bearer tok"


def test_mattermost_without_a_channel_says_so():
    verbindung = _verbindung("mattermost", "https://stub.local", token="tok")
    with pytest.raises(ConnectorError) as fehler:
        MattermostConnector(verbindung).post("Hallo")
    assert "Kanal" in str(fehler.value)


def test_sharepoint_without_graph_token_explains_the_requirement():
    verbindung = _verbindung("sharepoint", "https://graph.microsoft.com/v1.0")
    with pytest.raises(ConnectorError) as fehler:
        SharePointConnector(verbindung).search("Rechnung")
    assert "App-Registrierung" in str(fehler.value)
    assert "Zustimmung" in str(fehler.value)


def test_webex_search_filters_rooms():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rooms"
        return httpx.Response(
            200,
            json={"items": [{"id": "r1", "title": "Team Büro"}, {"id": "r2", "title": "Andere"}]},
        )

    verbindung = _verbindung("webex", "https://webexapis.com/v1", access_token="t")
    raeume = WebexConnector(verbindung, client=_client(handler)).search("Büro")

    assert [r.title for r in raeume] == ["Team Büro"]


def test_not_configured_is_a_distinct_error():
    """Fehlende Verbindung ist etwas anderes als ein Fehler des Dienstes."""
    assert issubclass(ConnectorError, RuntimeError)
    assert not issubclass(NotConfigured, ConnectorError)


# --- Verbindungen je Nutzer (Datenbank) -------------------------------------

DB_URL = __import__("os").environ.get("OA_TEST_DB_URL", "")


@pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt")
@pytest.mark.integration
def test_connection_is_stored_encrypted_and_per_user():
    from cryptography.fernet import Fernet

    from officeassistant.store import db
    from officeassistant.store.connections import ConnectionError_, ConnectionStore

    key = Fernet.generate_key().decode()
    conn = db.connect(DB_URL, autocommit=True)
    db.migrate(conn)
    conn.execute(
        "TRUNCATE connection, app_user RESTART IDENTITY CASCADE"
    )
    conn.execute(
        "INSERT INTO app_user (id, email, display_name) VALUES "
        "('u-a', 'a@example.org', 'A'), ('u-b', 'b@example.org', 'B')"
    )
    speicher = ConnectionStore(conn, key)
    speicher.save("u-a", "jira", "https://firma.atlassian.net", {"email": "a@x", "token": "geheim"})

    meine = speicher.of_user("u-a")
    fremde = speicher.of_user("u-b")

    assert [v.kind for v in meine] == ["jira"]
    assert meine[0].secret["token"] == "geheim"
    assert fremde == []

    roh = conn.execute("SELECT encode(ciphertext, 'escape') AS inhalt FROM connection").fetchone()
    assert "geheim" not in str(roh["inhalt"])

    with pytest.raises(ConnectionError_):
        speicher.one("u-b", "jira")
    conn.close()


@pytest.mark.skipif(not DB_URL, reason="OA_TEST_DB_URL nicht gesetzt")
@pytest.mark.integration
def test_skype_is_refused_with_a_reason():
    from cryptography.fernet import Fernet

    from officeassistant.store import db
    from officeassistant.store.connections import ConnectionStore

    conn = db.connect(DB_URL, autocommit=True)
    speicher = ConnectionStore(conn, Fernet.generate_key().decode())
    with pytest.raises(ValueError) as fehler:
        speicher.save("u-a", "skype", "https://skype.example", {})
    assert "abgeschaltet" in str(fehler.value)
    conn.close()


def test_jira_reports_the_retired_search_endpoint():
    """Atlassian hat /rest/api/2/search abgeschaltet (CHANGE-20, Antwort 410)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, text='{"errorMessages":["The requested API has been removed"]}')

    with pytest.raises(ConnectorError) as fehler:
        JiraConnector(
            _verbindung("jira", "https://stub.local", email="a@example.org", token="t"),
            client=_client(handler),
        ).search("Postfach")

    assert "abgeschaltet" in str(fehler.value)


def test_mattermost_reads_posts_oldest_first():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v4/channels/kanal-1/posts"
        return httpx.Response(
            200,
            json={
                "order": ["p2", "p1"],
                "posts": {
                    "p1": {"id": "p1", "user_id": "u1", "message": "Erst", "create_at": 1},
                    "p2": {"id": "p2", "user_id": "u2", "message": "Dann", "create_at": 2},
                },
            },
        )

    verbindung = _verbindung("mattermost", "https://stub.local", token="tok")
    posts = MattermostConnector(verbindung, client=_client(handler)).posts("kanal-1")

    assert [p["text"] for p in posts] == ["Erst", "Dann"]
