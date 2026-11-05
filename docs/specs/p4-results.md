# P4 — Team, Routinen, Freigaben: Stand

Datum: 2026-11-05
Auftrag: SPEC-Abschnitt 7, Phase P4.

## Stand je Punkt

| # | Aufgabe | Stand | Beleg |
|---|---|---|---|
| P4.1 | Team: Leitung + Posteingang, Entwurf, Termine, Recherche; deutsche Anweisungen | **fertig** | 5 Tests, zwei echte Läufe über die API |
| P4.2 | Routine *Morgenbriefing* (08:00) | **fertig** | Lauf über den Zeitgeber, Ergebnis in `routine_run` und auf `/routinen` |
| P4.3 | Routine *Inbox-Triage* (nur Kennzeichnen) | **teilweise** | Lauf liest und ordnet; Kennzeichnen mit Freigabe noch nicht geübt |
| P4.4 | Routine *Meeting-Vorbereitung* | **fertig, ohne Kalender** | Lauf antwortet „Heute keine Termine." (IMAP hat keinen Kalender) |
| P4.5 | Freigabe-Eingang: Liste, Vorschau, Freigeben/Ablehnen, Fortsetzen | **fertig** | `p2-results.md`, Seite `/freigaben` |
| P4.6 | Routine-Editor in einfacher Sprache | **fertig** | 8 Tests, im Browser angelegt und geändert |
| P4.7 | Gedächtnis aus Korrekturen, sichtbar und änderbar | offen | — |
| P4.8 | Aktivitätsansicht je Nutzer (Läufe, Werkzeuge, Token) | **fertig, ohne Tokenzählung** | Seite `/aktivitaet` mit Läufen, Werkzeugen und Protokoll |

## P4.1 im Einzelnen

Datei: `src/officeassistant/agents/team.py`, eingehängt in `api/main.py` als
`teams=[office-team]`.

| Rolle | Kennung | Werkzeuge |
|---|---|---|
| Leitung | `office-team` | keine; verteilt nur (`TeamMode.route`) |
| Posteingang | `triage` | `search_mail`, `read_mail`, `label_mail`, `archive_mail` |
| Entwurf | `entwurf` | `search_mail`, `read_mail`, `create_draft` |
| Termine | `termine` | `list_calendar`, `search_mail`, `read_mail` |
| Recherche | `recherche` | `search_mail`, `read_mail` |

**Keine Rolle hat `send_draft`.** Senden bleibt beim Menschen; das prüft ein Test über alle
Rollen.

Der Leitung sind die Zuständigkeiten als Regeln mitgegeben („Posteingang ordnen → Posteingang",
„Termine, Kalender, Verfügbarkeit → Termine", …) und die Anweisung, selbst keine Fachaufgabe
auszuführen.

## Nachweise

### Tests

`tests/test_team.py` — 5 Prüfungen ohne Netz:

* vier Rollen in fester Reihenfolge,
* keine Rolle darf senden,
* jede Rolle sieht nur ihre Werkzeuge,
* alle Anweisungen sind deutsch und verbieten das Senden,
* die Leitung nennt alle vier Rollen und führt nichts selbst aus.

### Läufe über die API

| Auftrag | Ergebnis | Geantwortet hat |
|---|---|---|
| „Welche Termine habe ich morgen?" | „Der Kalender kann derzeit nicht über IMAP abgerufen werden … Microsoft Graph erforderlich." | `termine` |
| „Fasse die Nachricht Rechnung 4711 zusammen." | Zusammenfassung mit Absender, Datum, Betreff | `recherche` (Werkzeug `delegate_task_to_member`) |

Beide Läufe endeten mit `COMPLETED`. Die Leitung hat also weitergegeben statt selbst zu
antworten.

Gegenprobe, dass die Werkzeuge selbst tragen: Auftrag an den Einzelagenten
„Lies die Nachricht mit dem Betreff Rechnung 4711 und gib den vollständigen Text wieder."
liefert den Text der Testnachricht („Bitte bis Freitag zahlen. Betrag: 120 EUR.").

## Offen

P4.2–P4.4 brauchen den Zeitplaner (Agno-Scheduler bzw. System-Cron), P4.6 einen Editor,
P4.7 die Wissensbasis, P4.8 eine Ansicht über `audit` und die Agno-Läufe.

## P4.2 bis P4.4: was jetzt läuft

Zeitgeber: `deploy/oa-routine.service` und `oa-routine.timer` als systemd-Nutzerdienste,
jede Minute, Aufruf `scripts/run_routine.py --due`. Eine Routine feuert, wenn ihr
Cron-Ausdruck in der laufenden Minute zutrifft und in der Minute davor nicht.

```
$ systemctl --user list-timers oa-routine.timer
NEXT                        LEFT  UNIT             ACTIVATES
Thu 2026-11-05 15:57:00 CET  15s  oa-routine.timer oa-routine.service
$ systemctl --user status oa-routine.service
Process: … (code=exited, status=0/SUCCESS)
uv[…]: Nichts fällig.
```

### Nachweis, dass der Zeitgeber eine Routine wirklich startet

Cron des Morgenbriefings vorübergehend auf `* * * * *` gesetzt, eine Minute gewartet:

```
$ podman exec oa-pg-test psql -U oa -d oa -tAc "select id,status from routine_run order by id desc limit 1"
3|completed
```

Danach zurück auf `0 8 * * 1-5`.

### Läufe der drei Routinen

| Routine | Werkzeuge im Lauf | Ergebnis |
|---|---|---|
| Morgenbriefing | `list_calendar`, `search_mail` | Kalender nicht verfügbar (IMAP), 20 Nachrichten im Posteingang genannt, keine offenen Aufgaben behauptet |
| Posteingang ordnen | `search_mail`, 8× `read_mail` | acht Zeilen mit Absender, Betreff, Einordnung |
| Terminvorbereitung | `list_calendar` | „Heute keine Termine." |

### Zwei Fehler, die dabei auffielen und behoben sind

1. **Erfundene Termine.** Im ersten Lauf warf `list_calendar` bei IMAP eine Ausnahme; das
   Modell erfand daraufhin Termine, Uhrzeiten und Nachrichtenkennungen. Das Werkzeug
   liefert jetzt eine Auskunft (`[{"hinweis": "IMAP kennt keinen Kalender …"}]`) statt eines
   Fehlers. Der nächste Lauf nennt die Grenze und erfindet nichts.
2. **Kontextfenster gesprengt.** Die Triage las alle 20 Nachrichten im Volltext
   (`Context size has been exceeded`). `read_mail` kürzt den Text jetzt auf 4000 Zeichen
   und meldet `gekuerzt: true`; die Triage liest höchstens acht Nachrichten.

Damit das nicht wieder unbemerkt bleibt, protokolliert der Läufer die Werkzeugnamen:

```
Routine inbox-triage: Werkzeuge ['search_mail', 'read_mail', 'read_mail', …]
```

### Seite `/routinen`

Zeigt die eingerichteten Routinen (Name, Zeitplan, Vertrauensstufe, Zustand) und die
letzten fünf Läufe mit Stand und Text. Im Browser geprüft, drei Routinen sichtbar.

### Tests

`tests/test_routines.py` — 6 Prüfungen: Speichern und Finden, Ändern statt Verdoppeln,
ungültiger Zeitplan wird mit deutschem Satz abgewiesen, Fälligkeit nur in der Minute,
Lauf wird mit Text abgelegt, gescheiterter Lauf wird mit Grund abgelegt.

Dazu in `tests/test_mail_tools.py`: langer Nachrichtentext wird gekürzt.

## P4.6: der Editor auf `/routinen`

Ohne Editor konnte nur ändern, wer SQL schreibt. Das war eine Lücke, nicht eine
Einschränkung.

Die Seite hat jetzt drei Karten:

1. **Eingerichtete Routinen** — Name, Auftrag (gekürzt), Zeitplan, Vertrauensstufe,
   Zustand, dazu je Zeile „ausschalten"/„einschalten" und „Löschen".
2. **Routine anlegen oder ändern** — Name, Zeitplan (Auswahl in einfacher Sprache), Auftrag
   als Freitext, Vertrauensstufe. Gleicher Name überschreibt die bestehende Fassung.
3. **Letzte Läufe** — die fünf jüngsten Läufe mit Stand und Text.

Zeitplan in Alltagssprache — **ein Cron-Ausdruck kommt in der Oberfläche nicht vor**:

| Frage auf der Seite | Auswahl |
|---|---|
| Wie oft? | Jeden Tag · Werktags (Montag bis Freitag) · An einem Wochentag · Einmal im Monat · Alle … Minuten · Alle … Stunden |
| Uhrzeit (HH:MM) | Freitext, z. B. `08:00` |
| Wochentag | Montag bis Sonntag |
| Tag im Monat | 1 bis 28 |
| Abstand | Zahl bei „Alle … Minuten/Stunden" |

Die Tabelle zeigt den Zeitplan wieder als Satz: „werktags um 08:00", „alle 30 Minuten
zwischen 7 und 19 Uhr, werktags", „am 15. jedes Monats um 09:00". Ein Ausdruck, den die
Seite nicht kennt, wird als „unbekannter Zeitplan (…)" angezeigt und nicht beschönigt.

Falsche Angaben werden mit einem Satz abgewiesen, bevor etwas gespeichert wird:
„Bitte die Uhrzeit als HH:MM angeben, zum Beispiel 08:00.", „Bitte für den Abstand in
Minuten eine Zahl eintragen.", „Tag im Monat muss zwischen 1 und 28 liegen."

**Abweichung von der SPEC:** dort steht „Routine editor in plain language (prompt + cron +
trust)". Der Cron-Teil ist bewusst nicht umgesetzt: eine Bürokraft soll keinen
Cron-Ausdruck schreiben. Die Übersetzung liegt in `routines/schedule.py` und ist durch
18 Tests abgedeckt.

### Nachweis

**Im Browser** (echter Klick, nicht nur HTTP): Name und Auftrag getippt, „Routine
speichern" geklickt → Weiterleitung mit „Routine gespeichert: wochenbericht", Zeile
`5|wochenbericht|0 8 * * 1-5|read-only|t` in der Datenbank. Die Zeile und der Datensatz
wurden danach wieder entfernt.

**Tests** (`tests/test_routines_page.py`, 8 Prüfungen): Anlegen über die Auswahl, eigener
Cron-Ausdruck, falscher Ausdruck wird abgewiesen und nichts gespeichert, leerer Name wird
abgewiesen, gleicher Name ändert statt zu verdoppeln, Abschalten und Einschalten, Löschen,
und: eine fremde Routine bleibt bei Löschen und Abschalten unberührt.

`OA_TEST_IMAP=1 OA_TEST_DB_URL=… uv run pytest` → **87 passed**.

### Fehler beim Bau des Editors

Die Beschriftungen lauteten zunächst `Tag im Monat (nur bei „Einmal im Monat")`. Das
deutsche schließende Anführungszeichen `"` ist zugleich das Zeichen, das einen
HTML-Attributwert beendet. Angezeigt wurde deshalb `Tag im Monat (nur bei „Einmal im Monat`
— der Rest fiel weg. Dasselbe bei `Abstand`.

Behebung: keine Anführungszeichen mehr in Attributwerten; Beschriftungen lauten jetzt
„Tag im Monat (gilt nur bei Einmal im Monat)" und „Abstand in Minuten oder Stunden".

`tests/test_ui_markup.py` liest das erzeugte HTML mit einem Parser und prüft: jedes Feld
hat `data-name` und `_label`, jede Klammer ist geschlossen, kein Anführungszeichen steht im
Attributwert, die Zahl der Anführungszeichen ist gerade.

## Befugnis je Routine (Nachtrag zu P4.6)

Vorher bekam jede eigene Routine stillschweigend die Lese-Werkzeuge, ohne dass die Seite
das sagte. Jetzt wählt der Nutzer es aus, und die Seite zeigt es.

| Auswahl auf der Seite | Werkzeuge im Lauf | Vertrauensstufe |
|---|---|---|
| Nur lesen | `search_mail`, `read_mail`, `list_calendar` | `read-only` |
| Lesen und kennzeichnen | dazu `label_mail`, `archive_mail` | `approval-required` |
| Lesen und Entwürfe schreiben | dazu `create_draft` | `approval-required` |

`send_draft` steht in keiner Stufe. Unter der Auswahl steht: „Senden ist in keiner Stufe
enthalten. Nachrichten gehen erst hinaus, wenn ein Mensch sie freigibt."

Die zweite Frage nach der Vertrauensstufe ist entfallen: sie folgt aus der Befugnis
(`TRUST_FOR_SCOPE`), sonst stand in der Tabelle „Nur lesen / nur lesen".

Gespeichert wird die Befugnis in `routine.scope` (Schema-Version 5, Werte `read`, `label`,
`draft`); der Läufer wählt die Werkzeuge danach, nicht nach dem Namen der Routine. Die drei
mitgelieferten Routinen behalten ihre festen Vorgaben.

### Nachweis

Im Browser eine Routine `entwurfstest` mit „Lesen und Entwürfe schreiben" angelegt:

```
$ podman exec oa-pg-test psql -U oa -d oa -tAc \
    "select name,cron,trust,scope from routine where name='entwurfstest'"
entwurfstest|0 8 * * *|approval-required|draft

$ uv run python scripts/run_routine.py --name entwurfstest --user alice@example.org
Routine entwurfstest: Werkzeuge ['create_draft']
Der Entwurf wurde erfolgreich unter der ID "Drafts|19" mit dem Betreff "Test" an
bob@example.org angelegt.
```

Der Lauf hat also nur das Werkzeug benutzt, das die Befugnis zulässt, und den Entwurf im
echten Postfach abgelegt. Die Testroutine wurde danach entfernt.

### Dazu behoben

* Platzhalter sind keine Werte: Uhrzeit, Tag im Monat und Abstand sind jetzt vorbelegt
  (`_value`), sonst kam „Bitte die Uhrzeit als HH:MM angeben" bei leerem Feld, obwohl
  „08:00" als Platzhalter zu sehen war.
* `tests/test_ui_markup.py` prüft zusätzlich, dass diese Vorgaben im HTML stehen.

Tests: `tests/test_routines.py` und `tests/test_routines_page.py` decken Speichern der
Befugnis, Werkzeuge je Befugnis, Ablehnung einer unbekannten Befugnis und die Ableitung der
Vertrauensstufe ab.

## P4.7: Gedächtnis

Der Assistent lernt aus Korrekturen und merkt sich Sätze — je Nutzer getrennt.

| Teil | Datei |
|---|---|
| Ablage | `store/memory.py` (Tabelle `memory_entry`, vorhanden seit P1) |
| Werkzeug | `agents/memory_tools.py`: `remember(fact, kind)` |
| Wirkung im Lauf | `memory_instructions(run_context)`, als aufrufbare Anweisung am Agenten |
| Seite | `ui/memory_page.py`: `/gedaechtnis` — Liste, Ergänzen, Löschen |

Arten: Person, Projekt, Schreibstil, Sonstiges. Doppelte Sätze werden nicht zweimal
gespeichert. Höchstens 200 Sätze gehen in einen Lauf; mehr wäre Ballast.

### Nachweis

Lauf 1 über die API:

> „Merken Sie sich bitte: Ich möchte immer mit Sie und ohne Vornamen angesprochen werden."

```
Status: COMPLETED
Werkzeuge: ['remember']
memory_entry: 1 | person | Der Nutzer möchte immer mit Sie und ohne Vornamen
              angesprochen werden. | chat
```

Lauf 2, neue Frage ohne diesen Satz im Gespräch:

> „Wie soll ich Sie ansprechen?"

> „Ich möchte Sie mit „Sie" ansprechen und ohne Vornamen."

Der Satz kommt also aus dem Gedächtnis. Die Seite `/gedaechtnis` zeigt ihn, mit „Löschen"
je Zeile (im Browser geprüft).

**Ehrlich:** belegt ist, dass eine spätere **Antwort** die Merksätze beachtet. Dass ein
**Entwurf** sie beachtet, ist derselbe Mechanismus, aber nicht eigens geprüft.

## P4.8: Aktivitätsansicht

`ui/activity_page.py`, Seite `/aktivitaet`, zwei Karten:

* **Läufe** — Zeit, wer (`agent_id`/`team_id`), Stand, benutzte Werkzeuge, aus `ai.agno_runs`
  gefiltert nach `user_id`.
* **Protokoll der Werkzeugaufrufe** — Zeit, Werkzeug, Ergebnis, aus `audit`, ebenfalls
  nach Nutzer gefiltert.

Im Browser geprüft — vier Läufe sichtbar, darunter einer mit `remember` und einer mit
`search_mail, read_mail`.

**Nicht enthalten:** Tokenzählung. Die SPEC nennt „runs, tool calls, tokens"; die Zahl der
verbrauchten Token steht in den Laufdaten, wird aber noch nicht angezeigt.
