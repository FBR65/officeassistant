# Drei Arbeitsseiten: Post, Chat, Kalender

Datum: 2026-11-05
Auftrag: Der Nutzer soll nicht mehr zwischen Mailprogramm und Chatprogramm wechseln.
Freigaben des Nutzers: Kalender über ICS, Graph vorbereitet; Chat alle 5 Sekunden neu laden;
Senden im Chat per Klick.

## Die Seiten

| Seite | Inhalt | Quelle |
|---|---|---|
| `/post` | Posteingang (25 Nachrichten), Nachricht lesen, Antwort entwerfen | Anbieter des Nutzers (IMAP) |
| `/chat` | Kanäle, Verlauf, Nachricht schreiben, Takt 5 s | Mattermost |
| `/kalender` | Woche Montag bis Sonntag, Blättern, ganztägige Termine | ICS-Abo/Datei; Graph vorbereitet |

Gemeinsame Navigation und Kopfzeile; der Wechsel zwischen den Programmen entfällt.

## Was jede Seite tut und was nicht

**Post** liest über `resolve_session` das Postfach des angemeldeten Nutzers. Ein Klick auf
eine Zeile öffnet die Nachricht; darunter steht ein Antwortformular mit Empfänger und
`Re: …` vorbelegt. „Entwurf anlegen" legt den Entwurf im Postfach ab (`Drafts`). **Gesendet
wird nicht** — das bleibt bei der Freigabe.

**Chat** zeigt die Kanäle des ersten Teams. Der Verlauf wird alle fünf Sekunden neu geholt
und ersetzt. „Senden" schickt die Nachricht sofort, wie in Mattermost selbst.

**Kalender** liest eine ICS-Adresse oder Datei, löst Wiederholungen auf
(`recurring-ical-events`) und zeigt Werktage und Wochenende. Ohne Quelle nennt die Seite den
Weg zur Einrichtung.

## Nachweise

### Kalender gegen eine echte ICS-Datei

`tests/data/kalender.ics` enthält drei Termine, darunter eine wöchentliche Wiederholung.
8 Tests in `tests/test_calendar_ics.py`: Woche, Zeit/Ort/Teilnehmer, ganztägig,
Wiederholung in mehreren Wochen, Termine außerhalb des Fensters, fehlende Datei, kaputte
Daten, Graph ohne Token.

Im Browser: „Woche vom 02.11.2026 bis 08.11.2026", Montag mit „15:00 – 16:00 Jour fixe".

### Chat gegen einen Mattermost-Ersatz

`scripts/fake_mattermost.py` beantwortet genau die Aufrufe, die die Seite braucht.
Verbindung auf `http://127.0.0.1:8065` eingerichtet, Seite geöffnet:

* Kanäle `#allgemein`, `#buero`
* Verlauf mit zwei Nachrichten
* Nachricht getippt, „Senden" geklickt → erscheint im Verlauf
* Nachricht von außen abgelegt → **ohne Neuladen** nach dem Takt sichtbar (5-Sekunden-Takt
  belegt)

### Post gegen das echte IMAP-Postfach

Posteingang mit den Testnachrichten, Nachricht geöffnet, Antwort formuliert, „Entwurf
angelegt" geklickt:

```
/post?meldung=Entwurf angelegt: Drafts|26
```

Der Entwurf liegt damit im Ordner `Drafts` des Postfachs.

### Tests

```
OA_TEST_IMAP=1 OA_TEST_DB_URL=… uv run pytest   → 149 passed
```

## Grenzen

* **Chat**: gegen einen Ersatzdienst geprüft, nicht gegen ein echtes Mattermost. Die
  Nutzerkennungen werden als Kurzform angezeigt; Namen aufzulösen wäre ein weiterer Aufruf
  je Nachricht.
* **Kalender**: nur ICS. Microsoft Graph ist als Adapter vorhanden
  (`connectors/graph_calendar.py`) und sagt ohne Token, was fehlt.
* **Post**: kein Gmail, kein Graph — die Anbieter fehlen (P2.1, P3.1).
* **Senden im Chat** umgeht die Freigabe bewusst: der Mensch klickt selbst. Für Nachrichten,
  die das Modell schreiben soll, gilt weiter die Freigabe-Regel.
* Der Mattermost-Ersatz und der Testcontainer `oa-mail` laufen nur zur Prüfung.
