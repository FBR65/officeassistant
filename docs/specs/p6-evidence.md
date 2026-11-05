# P6 — Nachweis je Anforderung

Datum: 2026-11-05. Spalten: Anforderung | umgesetzt | Prüfung | Beleg.
„vorbereitet" heißt: Code vorhanden, aber nicht gegen den echten Dienst oder nicht im Betrieb geprüft.

## P0 — Spikes

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| P0.1 KoliBri in NiceGUI | ja | Spike | `p0-results.md`, `spikes/p0_1_kolibri` |
| P0.2 Freigabe übersteht Neustart | ja | Spike | `p0-results.md` |
| P0.3 Keycloak + LDAP, Nutzertrennung | ja | Spike | `p0-results.md` |
| P0.4 Werkzeugaufruf über llama-swap | ja | Spike | `p0-results.md` |
| P0.5 Gmail nur lesen mit eigenem Token | **nein**, fremder Consent | — | `p0-results.md` |
| P0.6 Graph über Device Code | nein | — | kein Mandant |
| P0.7 IMAP gegen Exchange on-prem | ja, über P3.5 nachgeholt | Tests gegen GreenMail | `p3-results.md` |

## P1 — Gerüst und IAM

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| Abhängigkeiten gesperrt | ja | `uv sync` | `p1-results.md` |
| Einstellungen mit klarer Meldung | ja | `tests/test_settings.py` | `p1-results.md` |
| Anbieter-Vertrag + Testanbieter | ja | `tests/test_provider_contract.py` | — |
| Schema und Migration | ja | `tests/test_store_integration.py` (Version 6) | — |
| Nutzerverwaltung, Rollen | ja | `tests/test_session_integration.py` | — |
| Verschlüsselter Token-Speicher | ja | `tests/test_store_integration.py` | — |
| Protokoll (nur anhängend) | ja | Trigger in `schema.sql` | — |
| AgentOS mit JWT und Nutzertrennung | ja | `p0-results.md`, `/health` 200 | — |
| NiceGUI-Hülle mit Anmeldung | ja | im Browser geprüft | — |
| Containerfiles und Quadlets | gebaut, **nicht gestartet** | Build erfolgreich | `deploy/README.md` |

## P2 — Gmail

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| P2.1 Gmail anbinden, Kontenliste, Trennen | **ja**, aber über IMAP mit App-Kennwort statt OAuth | `tests/test_provider_wiring.py`, echter Login und Agentenlauf | `p2-1-gmail-results.md` |
| P2.2 Suche und Lesen, Text ohne HTML | ja | `tests/test_mail_tools.py` | — |
| P2.3 Entwurf und Senden mit Freigabe | ja | `p2-results.md` (Lauf pausiert, freigegeben, gesendet) | — |
| P2.4 Kennzeichnen und Ablegen mit Stufen | ja | `tests/test_mail_tools.py` | — |
| P2.5 Werkzeuge am Adapter des Aufrufers | ja | Agentenlauf | — |

## P3 — Microsoft-Pfade

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| P3.1 Graph-Anmeldung | nein | — | kein Mandant |
| P3.2 Graph-Suche | nein | — | — |
| P3.3 Graph-Entwurf | nein | — | — |
| P3.4 Graph-Kalender | nein | — | — |
| P3.5 IMAP/SMTP | ja | 8 Tests gegen GreenMail, Agentenlauf | `p3-results.md` |
| P3.6 Anbieterwahl je Konto | teilweise (imap/fake) | Seite `/postfaecher` | — |

## P4 — Agenten, Routinen, Freigaben

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| P4.1 Team mit vier Rollen | ja | `tests/test_team.py`, zwei Läufe | `p4-results.md` |
| P4.2 Morgenbriefing | ja | Lauf über den Zeitgeber | `p4-results.md` |
| P4.3 Inbox-Triage | teilweise: liest und ordnet; Kennzeichnen mit Freigabe ungeübt | Lauf | `p4-results.md` |
| P4.4 Terminvorbereitung | ja, ohne Kalender (IMAP) | Lauf | `p4-results.md` |
| P4.5 Freigabe-Eingang | ja | Seite `/freigaben`, Demo-Lauf | `p2-results.md` |
| P4.6 Routine-Editor | ja, Zeitplan in Alltagssprache | 8 Seitentests, im Browser | `p4-results.md` |
| P4.7 Gedächtnis | ja | 9 Tests, zwei Läufe | `p4-results.md` |
| P4.8 Aktivitätsansicht | ja, mit Tokenzahl | im Browser | `p4-results.md` |

## P5 — Barrierefreiheit und Auslieferung

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| P5.1 KoliBri in allen Ansichten | überwiegend: alle Nutzeransichten aus `kol-*`, Tabellen und Auswahlfelder bleiben natives HTML | Sichtprüfung | offen: systematische Zählung |
| P5.2 Tastatur, Fokus, Fehlermeldungen | nein | — | offen |
| P5.3 Themenwechsel Standard/BWSt | **vorbereitet, nicht freigegeben**: BWSt-Paket eingebunden, Seite verliert ohne Schrift- und Icon-Assets die Darstellung → Schalter wieder entfernt | Versuch dokumentiert | `p4-results.md` |
| P5.4 Verwaltungsbereich | nein | — | offen |
| P5.5 Proben gegen Einschleusung | ja | `tests/test_prompt_injection.py`, 6 Prüfungen | — |
| P5.6 Betriebshandbuch | teilweise: `deploy/README.md` vorhanden, ohne Gmail- und Entra-Anleitung | — | offen |

## Anbindungen (gewünschte Dienste)

| Dienst | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| Jira | ja (Suche, Anlegen, Kommentar) | 5 Tests gegen Stub, echter Endpunkt antwortet | `connections-results.md` |
| Confluence | ja (Suche) | 2 Tests gegen Stub | — |
| Mattermost | ja (Kanäle, Senden) | 2 Tests gegen Stub | — |
| SharePoint | ja (Graph-Suche) | nur Verhalten ohne Token geprüft | — |
| OneNote | ja (Notizbücher) | nur Verhalten ohne Token geprüft | — |
| Webex | ja (Räume, Senden) | 1 Test gegen Stub | — |
| Skype | **nicht möglich** | Dienst abgeschaltet | `connections-results.md` |

## Arbeitsseiten (Auftrag vom 05.11.2026)

| Anforderung | umgesetzt | Prüfung | Beleg |
|---|---|---|---|
| Postfach lesen und antworten | ja | im Browser gegen IMAP, Entwurf `Drafts\|26` | `arbeitsseiten-results.md` |
| Chat lesen und senden | ja | gegen Mattermost-Ersatz, Takt belegt | — |
| Kalender als Woche | ja, ICS | 8 Tests, im Browser | — |
| Graph für den Kalender | vorbereitet | nur Verhalten ohne Token | — |

## Testbilanz

```
OA_TEST_IMAP=1 OA_TEST_DB_URL=… uv run pytest   → 151 passed
```

## Was das nicht ist

* Kein Betrieb hinter der Podman-Quadlet-Einheit (nur gebaut, nicht gestartet).
* Keine echten Microsoft- oder Google-Konten angebunden.
* Kein Lasttest, keine Barrierefreiheitsprüfung mit Hilfsmitteln, keine Freigabe durch
  einen Datenschutzbeauftragten.
