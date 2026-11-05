# Anbindungen außerhalb des Postfachs

Datum: 2026-11-05
Bezug: SPEC Abschnitt 1 (gewünschte Integrationen), Phase P3/P4.

## Was jetzt geht

| Dienst | Suchen | Schreiben | Stand |
|---|---|---|---|
| Jira | Vorgänge über JQL | Vorgang anlegen, kommentieren | Adapter fertig, gegen echten Atlassian-Endpunkt geprüft (ohne gültigen Mandanten) |
| Confluence | Seiten über CQL | — | Adapter fertig, gegen Stub geprüft |
| Mattermost | Teams suchen, Kanäle lesen | Nachricht senden | Adapter fertig, gegen Stub geprüft |
| SharePoint | Dateien und Listeneinträge (Graph) | — | Adapter fertig, **ohne Graph-Token nicht prüfbar** |
| OneNote | Notizbücher lesen (Graph) | — | Adapter fertig, Suche über Graph nicht möglich, sagt das |
| Webex | Räume lesen | Nachricht senden | Adapter fertig, gegen Stub geprüft |
| **Skype** | — | — | **nicht möglich**: Dienst abgeschaltet (Firmendienst 31.07.2021, Verbraucherdienst Mai 2025) |

## Aufbau

| Teil | Datei |
|---|---|
| Vertrag | `connectors/base.py` (`WorkspaceConnector`, `Connection`, `NotConfigured`) |
| Jira, Confluence | `connectors/atlassian.py` |
| Mattermost | `connectors/mattermost.py` |
| SharePoint, OneNote, Webex | `connectors/microsoft.py` |
| Ablage der Verbindungen | `store/connections.py`, Tabelle `connection` (Schema-Version 6) |
| Werkzeuge für den Agenten | `agents/connector_tools.py` |
| Seite | `ui/connections_page.py`, `/anbindungen` |

Zugangsschlüssel liegen als Fernet-Chiffrat in `connection.ciphertext`. Jeder Nutzer sieht
nur seine Verbindungen. Fehlt eine Verbindung, antwortet das Werkzeug mit einem deutschen
Satz, den das Modell wiedergeben soll — nicht mit einer erfundenen Auskunft.

## Nachweise

### Tests gegen Stubs (`tests/test_connectors.py`, 13 Prüfungen)

Geprüft wird je Dienst: richtiger Pfad, richtiger Kopf, richtige Übersetzung der Antwort,
klare Meldung bei Fehler und bei fehlenden Zugangsdaten. Dazu: Verbindungen sind je Nutzer
getrennt, liegen verschlüsselt, Skype wird mit Begründung abgewiesen.

### Gegen den echten Atlassian-Endpunkt

Beim ersten Versuch antwortete Jira mit **410**:

> „The requested API has been removed. Please migrate to the /rest/api/3/search/jql API."

Die alte Suche `/rest/api/2/search` ist also abgeschaltet. Der Adapter nutzt jetzt
`/rest/api/3/search/jql`; danach antwortet der Endpunkt mit `{"issues":[],"isLast":true}`.

Das ist der einzige echte Netzkontakt. Ein gültiger Mandant mit echten Vorgängen stand
nicht zur Verfügung.

## Was ausdrücklich fehlt

* **Live-Betrieb** gegen Jira, Confluence, Mattermost, SharePoint, OneNote und Webex.
  Ohne Zugangsdaten und, bei Graph, ohne Zustimmung eines Mandanten-Administrators ist das
  nicht möglich. Die Adapter sind gegen Stubs geprüft, nicht gegen die Dienste.
* **Schreiben mit Freigabe**: Jira-Kommentar und Mattermost-Nachricht sind als Werkzeug
  vorhanden, aber noch nicht an die Freigabe-Stufe (`@approval`) gehängt. Bis dahin gilt:
  sie werden nicht aufgerufen, weil sie nicht in der Werkzeugliste des Agenten stehen.
* **Skype**: technisch nicht möglich.
