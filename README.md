# OfficeAssistant

On-Premise-Büroassistent für Postfach, Kalender und wiederkehrende Büroarbeit. Das System
liest Postfächer, ordnet Nachrichten, entwirft Antworten und führt Routinen unbeaufsichtigt
aus. Schreibende Aktionen lösen erst nach einer Freigabe durch einen Menschen aus.

Alle Daten bleiben im eigenen Netz. Es gibt keinen Zugriff auf Cloud-Dienste des
Betreibers, keine Telemetrie und keinen anbieterspezifischen Code im Kern: das Sprachmodell
wird über einen OpenAI-kompatiblen Endpunkt angesprochen, die Identität über OpenID Connect.

## Inhalt

1. [Merkmale](#merkmale)
2. [Aufbau](#aufbau)
3. [Rollen, Rechte und Freigaben](#rollen-rechte-und-freigaben)
4. [Oberfläche](#oberfläche)
5. [Agenten und Werkzeuge](#agenten-und-werkzeuge)
6. [Anbindungen](#anbindungen)
7. [Voraussetzungen](#voraussetzungen)
8. [Einrichten](#einrichten)
9. [Starten](#starten)
10. [Konfiguration](#konfiguration)
11. [Tests](#tests)
12. [Betrieb mit Podman](#betrieb-mit-podman)
13. [Dokumentation](#dokumentation)
14. [Stand und Grenzen](#stand-und-grenzen)
15. [Lizenz](#lizenz)

## Merkmale

| Merkmal | Stand |
|---|---|
| Postfach lesen, suchen, Nachricht anzeigen | umgesetzt, gegen Gmail und einen IMAP-Testserver geprüft |
| Entwurf anlegen, antworten, senden | umgesetzt; Senden nur nach Freigabe |
| Kennzeichnen und Ablegen | umgesetzt; nur nach Freigabe |
| Kalender der Woche und Termine des Tages | umgesetzt für ICS-Quellen; Microsoft Graph vorbereitet, nicht geprüft |
| Morgenbriefing, Posteingang ordnen, Terminvorbereitung | umgesetzt als Routinen mit Zeitgeber |
| Routinen im Alltagsdeutsch planen („Werktags um 8:00") | umgesetzt; kein Cron-Ausdruck in der Oberfläche |
| Freigaben durch einen Menschen | umgesetzt; dauerhaft gespeichert, übersteht einen Neustart |
| Gedächtnis für Arbeitsanweisungen je Nutzer | umgesetzt |
| Mehrbenutzerbetrieb mit Anmeldung über Keycloak | umgesetzt |
| Nutzerverwaltung im Frontend | umgesetzt; nur für Verwaltungsrollen sichtbar |
| Anbindungen an Jira, Confluence, SharePoint, OneNote, Webex | umgesetzt als Lesesuche, gegen Adressen erprobt |
| Chat und Kalender in derselben Oberfläche | umgesetzt; Chat gegen einen Ersatzdienst geprüft |
| PowerPoint-Dateien erstellen, mit Tabellen, Diagrammen und Bildern | umgesetzt; Richtlinien werden vor dem Speichern geprüft |
| Zentrale Designvorlage für Präsentationen | umgesetzt; Vorlage gewinnt bei Schrift und Farbe |
| PDF und Bilder hochladen, Text lesen, Texterkennung | umgesetzt; Textlayer zuerst, sonst Texterkennung mit 200 dpi |

## Aufbau

```
Oberfläche (NiceGUI, KoliBri)  ──JWT──▶  AgentOS (Agno)  ──▶  Postfach-Adapter
      src/officeassistant/ui              src/officeassistant/api        │
                                              │                          │
                              Keycloak (OIDC) ─┴─▶ LDAP / später AD      │
                              PostgreSQL 16 (Sitzungen, Protokoll, Token)
```

| Baustein | Aufgabe | Ort |
|---|---|---|
| Oberfläche | Seiten, Formulare, Anmeldung, Weiterleitung an die API | `src/officeassistant/ui` |
| AgentOS | Agent `office-assistant` und Team `office-team`, Werkzeuge, Freigaben | `src/officeassistant/api` |
| Agenten | Werkzeuge für Postfach, Gedächtnis, Anbindungen; Teamrollen | `src/officeassistant/agents` |
| Anbieter | Gmail und Exchange über IMAP/SMTP, Testanbieter | `src/officeassistant/providers` |
| Anbindungen | Jira, Confluence, SharePoint, OneNote, Webex, Microsoft Graph | `src/officeassistant/connectors` |
| Routinen | Zeitplan in Alltagssprache, Ausführung, Ergebnisablage | `src/officeassistant/routines` |
| Datenhaltung | Schema, Nutzer, Sitzungen, Verbindungen, Gedächtnis, Protokoll | `src/officeassistant/store` |
| Kalender | ICS lesen, Wiederholungen auflösen | `src/officeassistant/calendar` |
| Präsentationen | Richtlinien, Bau der `.pptx`, Ablage, Vorschau als Bild | `src/officeassistant/presentations` |
| Dokumente | Hochladen, Textlayer lesen, Texterkennung, Seiten anzeigen | `src/officeassistant/documents` |
| Betrieb | Containerdateien, Quadlets, Realm-Export | `deploy` |

Die Anwendung kennt weder Verzeichnis noch Anbieter im Kern. Jeder Aufruf bekommt den
Adapter des angemeldeten Nutzers; Zugangsdaten liegen verschlüsselt je Nutzer und Dienst.

## Rollen, Rechte und Freigaben

Grundsatz: **Das System schreibt nicht ohne Menschen.** Es gibt keine Stufe, in der eine
Nachricht selbsttätig das Haus verlässt.

| Stufe | Wirkung | Werkzeuge |
|---|---|---|
| `read-only` | lesen und antworten | `search_mail`, `read_mail`, `list_calendar`, Suche in Anbindungen |
| `approval-required` | lesen und schreiben, aber jede Schreibaktion wartet auf Freigabe | zusätzlich `create_draft`, `label_mail`, `archive_mail`, `send_draft` |

Eine Routine wählt ihre **Befugnis**: „Nur lesen", „Lesen und kennzeichnen", „Lesen und
Entwürfe schreiben". Die Vertrauensstufe folgt daraus; `send_draft` ist in keiner Stufe
enthalten.

Läuft eine Aktion in eine Freigabe, hält der Lauf im Zustand `PAUSED`. Die Entscheidung
liegt dauerhaft in der Datenbank und übersteht einen Neustart. Nach der Freigabe arbeitet
der Lauf im Hintergrund weiter; die Oberfläche wartet nicht darauf und meldet deshalb auch
bei langer Laufzeit keinen Verbindungsabbruch.

Das Auflösen übernimmt ein Dienstkonto mit der Kennung `sa:approver-admin`, weil Agno bei
eingeschalteter Nutzertrennung nur administrative Kennungen auflösen lässt. Der Mensch
steht als `resolved_by` in der Entscheidung.

## Oberfläche

| Seite | Pfad | Inhalt |
|---|---|---|
| Übersicht | `/` | Termine des Tages, offene Freigaben, letzte Läufe, Auffälligkeiten |
| Post | `/post` | Nachrichtenliste, Nachricht lesen, Antwort entwerfen |
| Chat | `/chat` | Mattermost-Verlauf, alle fünf Sekunden neu, Senden per Klick |
| Kalender | `/kalender` | Woche von Montag bis Sonntag, Wiederholungen aufgelöst |
| Präsentationen | `/praesentationen` | Dateien erstellen, herunterladen, löschen; Vorschau als Bilder |
| Dokumente | `/dokumente` | PDF und Bilder hochladen, Text je Seite lesen, herunterladen, löschen |
| Aufträge | `/auftraege` | freier Auftrag an den Assistenten, letzte Antwort |
| Freigaben | `/freigaben` | offene Entscheidungen, freigeben oder ablehnen |
| Routinen | `/routinen` | Routinen anlegen, ändern, abschalten, löschen; letzte Läufe |
| Gedächtnis | `/gedaechtnis` | gemerkte Arbeitsanweisungen je Nutzer |
| Aktivität | `/aktivitaet` | Läufe mit Stand, Werkzeugen und Antwort |
| Postfächer | `/postfaecher` | verbundene Postfächer |
| Anbindungen | `/anbindungen` | Adressen und Schlüssel für Jira, Confluence und weitere |
| Verwaltung | `/verwaltung` | Nutzer anlegen, Rolle setzen, Zugang sperren; nur für `admin` und `owner` |

Die Navigation ist nach Aufgaben gruppiert (Arbeiten, Assistent, Verwalten). Der Eintrag
„Verwaltung" erscheint nur für Verwaltungsrollen; an „Freigaben" steht die Zahl offener
Entscheidungen. Die Oberfläche ist deutsch, in der Sie-Form.

## Agenten und Werkzeuge

| Werkzeug | Aufgabe | Freigabe |
|---|---|---|
| `search_mail` | Nachrichten suchen, mit Anriss | nein |
| `read_mail` | Nachricht lesen, Text auf 1500 Zeichen begrenzt, Länge wählbar | nein |
| `create_draft` | Entwurf anlegen | nein |
| `send_draft` | Entwurf senden | **ja** |
| `label_mail` | Nachricht kennzeichnen | **ja** |
| `archive_mail` | Nachricht ablegen | **ja** |
| `list_calendar` | Termine ab heute, Vorgabe sieben Tage, Ortszeit | nein |
| `remember` | Arbeitsanweisung merken | nein |
| `create_presentation` | PowerPoint-Datei aus Titel und Folien erstellen und ablegen | nein |
| `list_documents`, `read_document` | hochgeladene Dokumente auflisten und lesen | nein |
| `search_jira`, `search_confluence`, `search_sharepoint`, `search_onenote`, `search_webex` | Lesesuche in den Anbindungen | nein |

Das Team `office-team` verteilt Aufträge auf vier Rollen: `triage` (suchen, lesen,
kennzeichnen, ablegen), `entwurf` (suchen, lesen, Entwurf), `termine` (Kalender und Lesen)
und `recherche` (Anbindungen). `send_draft` liegt in keiner Rolle.

## Anbindungen

| Dienst | Weg | Stand |
|---|---|---|
| Gmail | IMAP `imap.gmail.com:993`, SMTP `smtp.gmail.com:587` mit App-Kennwort | geprüft |
| Exchange lokal | IMAP/SMTP, Zugangsdaten je Nutzer | geprüft gegen Testserver |
| Microsoft 365 / Exchange Online | Microsoft Graph, `/me/calendarView` | vorbereitet, ohne Mandant nicht prüfbar |
| Kalender | ICS-Adresse oder Datei | geprüft |
| Mattermost | REST, Verlauf und Senden | geprüft gegen Ersatzdienst |
| Jira | REST, Suche über `/rest/api/3/search/jql` | geprüft |
| Confluence, SharePoint, OneNote, Webex | REST-Lesesuche | geprüft |

Netzfehler werden zur Auskunft: Liefert ein Dienst keine Antwort, gibt das Werkzeug ein
Feld `fehler` mit einem Hinweis auf die Seite „Anbindungen" zurück, statt den Lauf
abzubrechen.

## Voraussetzungen

| Was | Version |
|---|---|
| Python | 3.12 |
| uv | 0.9 oder neuer |
| PostgreSQL | 16, Erweiterung `pgvector` empfohlen |
| Keycloak | 26 oder neuer, mit Verbund auf LDAP oder Active Directory |
| Sprachmodell | OpenAI-kompatibler Endpunkt, geprüft mit llama-swap, Kontextfenster mindestens 16384 Token |
| Node.js | nur zum Bereitstellen der KoliBri-Dateien |
| LibreOffice und Poppler | für die Vorschau der Präsentationen als Bild (`soffice`, `pdftoppm`) |

## Einrichten

```bash
git clone <repository> OfficeAssistant
cd OfficeAssistant
uv sync
cp .env.example .env          # Werte einsetzen; .env bleibt lokal (chmod 600)

# KoliBri selbst hosten, kein CDN
npm install --prefix assets
bash scripts/vendor_kolibri.sh

# Schlüssel für die verschlüsselte Ablage der Postfach-Token
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Schema anlegen; läuft auch beim Start der Oberfläche
uv run python -c "from officeassistant.settings import Settings; from officeassistant.store import db; db.migrate(db.connect(Settings.load().db_url))"
```

Keycloak: `deploy/realm-oa.json` importieren. Der Export enthält den Verbund auf OpenLDAP,
die Clients `oa-ui` und `oa-ui-member` sowie vier Attributzuordnungen. Ohne diese Zuordnungen
meldet Keycloak „User returned from LDAP has null username". Für Active Directory ändert
sich nur der Verbund, nicht der Code.

Die Schlüsseldatei des Ausstellers wird als Datei erwartet:

```bash
curl -fsS http://127.0.0.1:8180/realms/oa/protocol/openid-connect/certs -o /tmp/oa_jwks.json
export JWT_JWKS_FILE=/tmp/oa_jwks.json
```

## Starten

```bash
# Oberfläche
uv run officeassistant-ui                     # http://127.0.0.1:8099

# Agenten-API
set -a; . ./.env; set +a
JWT_JWKS_FILE=/tmp/oa_jwks.json uv run uvicorn officeassistant.api.main:app --port 7777
```

| Dienst | Vorgabe |
|---|---|
| Oberfläche | 127.0.0.1:8099 |
| Agenten-API | 127.0.0.1:7777 |
| Keycloak | 127.0.0.1:8180, Realm `oa` |
| PostgreSQL | 127.0.0.1:55432 (Container) |
| Sprachmodell | 127.0.0.1:8080/v1 (llama-swap) |

Ein Auftrag lässt sich auch ohne Oberfläche absetzen:

```bash
curl -X POST http://127.0.0.1:7777/agents/office-assistant/runs \
  -H "Authorization: Bearer <Zugangstoken>" \
  -F "message=Welche Mails brauchen heute eine Antwort?" \
  -F "stream=false" \
  -F "user_id=<Subjekt aus dem Token>"
```

## Konfiguration

Alle Werte kommen aus der Umgebung, mit dem Präfix `OA_`. Fehlt ein Pflichtwert, bricht der
Start mit einer deutschen Meldung ab, die den Variablennamen nennt.

| Variable | Bedeutung | Pflicht |
|---|---|---|
| `OA_MODEL_BASE_URL` | OpenAI-kompatibler Endpunkt | ja |
| `OA_MODEL_API_KEY` | Schlüssel des Endpunkts, bei lokalem Betrieb `none` | nein |
| `OA_ROLE_LEADER`, `OA_ROLE_DRAFTING`, `OA_ROLE_TRIAGE` | Modellnamen je Rolle | ja |
| `OA_DB_URL` | PostgreSQL-Adresse | ja |
| `OA_TOKEN_KEY` | Fernet-Schlüssel für Postfach-Token (44 Zeichen) | ja |
| `OA_OIDC_ISSUER` | Aussteller, zum Beispiel `http://127.0.0.1:8180/realms/oa` | ja |
| `OA_OIDC_CLIENT_ID`, `OA_OIDC_CLIENT_SECRET` | Client der Oberfläche | ja |
| `OA_OIDC_REDIRECT_URL` | Rückadresse nach der Anmeldung | nein |
| `OA_UI_HOST`, `OA_UI_PORT` | Bindeadresse der Oberfläche | nein |
| `OA_API_BASE_URL` | Adresse der Agenten-API | nein |
| `OA_KOLIBRI_DIR` | Verzeichnis der KoliBri-Dateien | nein |
| `OA_AGENT_ID` | Kennung des Agenten | nein |
| `OA_APPROVER_TOKEN` | Token des Dienstkontos, das Freigaben auflöst | ja für Freigaben |
| `OA_KEYCLOAK_REALM`, `OA_KEYCLOAK_ADMIN_USER`, `OA_KEYCLOAK_ADMIN_PASSWORD` | Zugang für die Nutzerverwaltung | nur für `/verwaltung` |
| `JWT_JWKS_FILE` | Datei mit den Schlüsseln des Ausstellers | ja für die API |
| `OA_DATA_DIR` | Ablage für erzeugte Dateien, zum Beispiel `data` | nein |
| `OA_PRESENTATION_TEMPLATE` | Pfad zur zentralen Designvorlage (`.pptx`); leer heißt eingebaute Gestaltung | nein |
| `OA_OCR_BASE_URL`, `OA_OCR_MODEL` | Endpunkt und Modell der Texterkennung, Vorgabe `http://127.0.0.1:8080/v1` und `paddleocr-vl` | nein |
| `OA_OCR_TIMEOUT_S`, `OA_OCR_DPI`, `OA_OCR_MIN_TEXTLAYER` | Zeitgrenze 180 s, 200 dpi, Schwelle 40 Zeichen | nein |
| `OA_MAX_UPLOAD_BYTES` | Obergrenze für hochgeladene Dateien, Vorgabe 20 MB | nein |
| `OA_TEST_DB_URL` | Testdatenbank für die Integrationstests | nur für Tests |

Kein Wert aus `.env.example` gehört ins Repository. `.env` ist in `.gitignore` eingetragen.

## Tests

```bash
uv run pytest                                        # Einheitstests
OA_TEST_DB_URL=postgresql://... uv run pytest        # alle Tests, mit Datenbank
uv run pytest -m integration                         # nur die Tests mit Außendienst
```

Stand: **185 Tests bestanden, 9 übersprungen**. Übersprungen werden Tests, die eine laufende
Datenbank oder einen Testserver verlangen. Die Tests decken unter anderem ab: Anmeldung und
Sitzungscookie, Werkzeuge des Postfachs, Freigaben über einen Neustart hinweg, Rollen des
Teams, Zeitpläne in Alltagssprache, Prompt-Einschleusung, Kennzahlen der Übersicht, die
Rechte der Verwaltungsseite und die Richtlinien der Präsentationen.

## Präsentationen

Ein Auftrag im Chat oder das Formular auf `/praesentationen` erzeugt eine `.pptx`. Beide Wege
enden in derselben Ablage und gelten denselben Richtlinien.

| Regel | Wert |
|---|---|
| Format | 16:9, 33,87 × 19,05 cm |
| Titel | 28–32 pt, dunkelgrau |
| Fließtext | 19 pt, Unterpunkt 17 pt |
| Stichpunkte | höchstens sechs je Folie |
| Textmenge | höchstens 60 Wörter je Folie |
| Notizen | auf jeder Folie Pflicht, mit Zeitangabe |
| Fußzeile | Titel und Foliennummer, grau, unten |
| Tabellen | Kopfzeile in Akzentfarbe, 12 pt |
| Diagramme | Balken, Balken quer, Kreis, Linie; echte PowerPoint-Diagramme |
| Bilder | aus dem Postfach oder vom Server, mit Beschriftung und Bildnachweis |

Verstößt eine Beschreibung gegen eine Regel, entsteht **keine** Datei; die Meldung nennt die
Folie und den Grund. Ist eine Designvorlage gesetzt, kommen Layout, Schrift und Farben aus
ihrem Master; Textmenge, Notizen und Fußzeile bleiben Pflicht.

```bash
# zentrale Vorlage setzen (Pfad in .env):  OA_PRESENTATION_TEMPLATE=/pfad/hausvorlage.pptx
uv run python scripts/demo_praesentation.py /tmp/demo     # Beispieldatei und Bilder
```

## Dokumente und Texterkennung

`/dokumente` nimmt PDF-Dateien sowie PNG und JPG an (bis 20 MB). Je Seite gilt:

1. Textlayer lesen. Ab 40 Zeichen gilt die Seite als gelesen.
2. Sonst die Seite mit 200 dpi zeichnen und an die Texterkennung geben
   (`paddleocr-vl` über den OpenAI-kompatiblen Endpunkt).
3. Ist die Erkennung nicht erreichbar, bleibt die Seite leer und der Grund steht dabei.

Angezeigt wird je Seite, aus welchem Verfahren der Text stammt. Der Assistent kann die
Dokumente lesen (`list_documents`, `read_document`) und daraus zum Beispiel eine Präsentation
bauen. Das Verfahren ist an DocPipeline angelehnt; Feldgewinnung und Benchmark sind nicht
übernommen.

## Betrieb mit Podman

Alles läuft im Benutzerkontext, ohne Ports nach außen außer dem, den ein Reverse Proxy
freigibt. Die Dienste hören nur auf 127.0.0.1.

```bash
podman build -f deploy/ui.containerfile -t localhost/oa-ui:0.1 .
podman build -f deploy/api.containerfile -t localhost/oa-api:0.1 .
cp deploy/*.container deploy/*.network deploy/*.service deploy/*.timer ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start officeassistant-db officeassistant-api officeassistant-ui
```

Einzelheiten, Kennwörter, Schlüsseldateien und der Zeitgeber für Routinen stehen in
`deploy/README.md`.


## Stand und Grenzen

Ehrlich benannt, damit niemand mehr erwartet, als geprüft ist:

- **Microsoft Graph ist nicht geprüft.** Ohne Entra-Mandanten und Zustimmung ließ sich der
  Weg nicht testen. Der Adapter liegt bei, die Seite zeigt ohne Token eine klare Meldung.
- **Gmail läuft über IMAP und SMTP mit App-Kennwort**, nicht über OAuth. Ein eigener
  OAuth-Client ist nicht eingerichtet.
- **Das Verzeichnis ist schreibgeschützt.** Keycloak führt den LDAP-Verbund mit
  `editMode: READ_ONLY`. Nutzer, die über die Verwaltungsseite angelegt werden, legt
  Keycloak deshalb im eigenen Bestand an. Für Nutzer im Verzeichnis muss der Verbund auf
  `WRITABLE` gestellt werden.
- **Der Chat ist gegen einen Ersatzdienst geprüft**, nicht gegen einen produktiven
  Mattermost-Server.
- **Der Kalender liest ICS.** CalDAV ist nicht angebunden; für Exchange Online fehlt Graph.
- **Die Anbindungen sind Lesesuchen.** Schreiben nach Jira, Confluence oder SharePoint gibt
  es nicht.
- **Routinen laufen über den Zeitgeber des Systems** (`scripts/run_routine.py --due`), nicht
  über einen eigenen Scheduler im Dienst.


## Lizenz

MIT
