# SPEC — Übersicht, Navigation und Verwaltung

**Stand:** 2026-11-05 · **Fassung:** 0.2 (freigegeben am 05.11.2026, umgesetzt) · **Bezug:** Anmerkungen 1–3 des Auftraggebers

Dieses Papier beschreibt nur die drei genannten Punkte. Es wird nichts umgesetzt, bevor es
freigegeben ist.

## 1. Ist-Zustand, geprüft im Quelltext

| Punkt | Befund | Stelle |
|---|---|---|
| Startseite | `kol-card` mit dem Titel „Übersicht", Inhalt: „Angemeldet als …" plus zwei Verweise auf andere Seiten. Keine Zahlen, keine Termine, keine offenen Entscheidungen. | `ui/app.py:80-84` |
| Navigation | elf gleichrangige Einträge in einer Liste, ohne Gruppierung | `ui/layout.py:16-28` |
| Rollen | `app_user.role` kennt `owner`, `admin`, `member`; `is_admin` ist vorhanden, wird aber von keiner Seite ausgewertet | `store/users.py:9-30` |
| Nutzerverwaltung | keine Seite; Nutzer entstehen beim ersten Anmelden (`upsert`) | — |
| Verzeichnis | Keycloak-LDAP-Verbund mit `editMode: READ_ONLY`; Realm ohne Rollen und Gruppen | `deploy/realm-oa.json` |

Damit ist die Anmerkung „eine Übersicht, die keine Übersicht anzeigt" im Quelltext bestätigt.

## 2. Ziel

1. Die Startseite zeigt den Arbeitsstand auf einen Blick.
2. Die Navigation ist nach Aufgaben gruppiert, nicht nach Bauart.
3. Eine Verwaltungsseite legt Nutzer an und setzt deren Rolle — nur für `admin` und `owner`.

## 3. Umfang A — Übersicht als Arbeitsstand

Die Seite `/` zeigt vier Blöcke, jeder mit Zahlen und einem Verweis auf die Detailseite:

| Block | Inhalt | Quelle |
|---|---|---|
| Heute | Termine des Tages mit Uhrzeit und Ort | Kalenderquelle (ICS), sonst Hinweis |
| Wartet auf Sie | Anzahl offener Freigaben, je mit Werkzeug und Kurztext | `ai.agno_approvals` |
| Zuletzt gelaufen | die letzten fünf Läufe: Zeit, Stand, erster Satz der Antwort | `ai.agno_runs` |
| Auffällig | fehlgeschlagene Läufe der letzten 24 Stunden, fällige oder fehlgeschlagene Routinen | `ai.agno_runs`, `routine`, `routine_run` |

Regeln:

* Ein Block ohne Daten zeigt einen Satz, der den Grund nennt („Keine Termine eingetragen."),
  nicht eine leere Fläche.
* Zahlen sind Verweise: „3 offene Freigaben" führt nach `/freigaben`.
* Kein Block zeigt fremde Daten: jede Abfrage ist auf `user_id` der Sitzung beschränkt.

## 4. Umfang B — Navigation

Drei Gruppen, innerhalb der Gruppe bleibt die bisherige Reihenfolge:

| Gruppe | Einträge |
|---|---|
| Arbeiten | Übersicht, Post, Chat, Kalender |
| Assistent | Aufträge, Freigaben, Routinen, Gedächtnis, Aktivität |
| Verwalten | Postfächer, Anbindungen, Verwaltung (nur `admin`/`owner`) |

Zusätzlich: gleicher Seitenkopf auf allen Seiten (Titel, ein Satz Zweck), Freigaben zeigen die
Anzahl offener Entscheidungen in der Navigation.

## 5. Umfang C — Verwaltungsseite `/verwaltung`

| Element | Verhalten |
|---|---|
| Liste | alle Nutzer aus `app_user`: Name, E-Mail, Rolle, Stand (aktiv/inaktiv), zuletzt angemeldet |
| Anlegen | Formular: Anzeigename, E-Mail, Anmeldename, Rolle. Legt den Nutzer im Verzeichnis an und danach in `app_user` |
| Rolle ändern | Auswahl `member`/`admin`; die eigene Rolle lässt sich nicht entziehen |
| Deaktivieren | setzt `app_user.active = false`; die Anmeldung bleibt im Verzeichnis möglich, die Oberfläche verweigert den Zutritt |
| Protokoll | jede Änderung schreibt eine Zeile in `audit` (wer, wen, was, wann) |

Zutritt: `app_user.is_admin` der Sitzung. Wer nicht `admin` oder `owner` ist, bekommt 403 mit
dem Satz „Diese Seite ist der Verwaltung vorbehalten."

### 5.1 Anlegen im Verzeichnis

Der LDAP-Verbund steht auf `READ_ONLY`. In diesem Zustand kann Keycloak keine Nutzer ins
Verzeichnis schreiben. Zwei Wege:

| Weg | Ablauf | Folge |
|---|---|---|
| **W1** Verzeichnis schreibbar (`editMode: WRITABLE`) | Oberfläche → Keycloak Admin-Schnittstelle → OpenLDAP | eine Quelle, Anmeldung und Verwaltung stimmen überein |
| **W2** Nur Keycloak-lokal | Oberfläche → Keycloak, Nutzer ohne Verzeichnisbezug | zwei Quellen; ein späterer Verzeichnisnutzer gleichen Namens bleibt ein zweiter Datensatz |

Empfehlung: **W1**. Er ändert die Betriebsart des Verbunds und braucht einen Neustart von
Keycloak sowie ein schreibberechtigtes Dienstkonto im Verzeichnis.

## 6. Nicht im Umfang

* Selbstbedienung (Passwort ändern, Konto löschen durch den Nutzer)
* Passwortrichtlinien, Zwei-Faktor, Einladungsmails
* Feine Rechte je Routine oder je Postfach
* Gestaltungsarbeit über die vorhandenen KoliBri-Komponenten hinaus

## 7. Offene Fragen

| Nr. | Frage | Vorschlag |
|---|---|---|
| F1 | Verzeichnis schreibbar machen (W1) oder nur Keycloak-lokal (W2)? | **offen.** Umgesetzt ist W2: Keycloak legt den Nutzer im eigenen Bestand an. Für W1 muss `editMode` auf `WRITABLE` gestellt werden. |
| F2 | Soll die Verwaltungsseite ein Startkennwort setzen, oder vergibt der Nutzer es beim ersten Anmelden? | Startkennwort, das beim ersten Anmelden geändert werden muss |
| F3 | Sollen `admin` und `owner` auch die Postfächer und Anbindungen **anderer** Nutzer sehen? | Nein, in dieser Fassung nicht |

## 8. Nachweise, die diese SPEC verlangt

| Nr. | Nachweis |
|---|---|
| N1 | `/` zeigt an einem Tag mit Termin, offener Freigabe und einem fehlgeschlagenen Lauf alle vier Blöcke mit richtigen Zahlen |
| N2 | Ein Nutzer ohne `admin` erhält auf `/verwaltung` 403 und den genannten Satz |
| N3 | Ein über die Seite angelegter Nutzer kann sich anmelden und sieht nur eigene Daten |
| N4 | Jede Änderung an einem Nutzer erzeugt eine Zeile in `audit` |
| N5 | Testlauf grün, Zahl der Tests vorher/nachher im Ergebnisbericht |

## 9. Ergebnis (05.11.2026)

| Nr. | Nachweis | Stand |
|---|---|---|
| N1 | `/` zeigt vier Blöcke mit Zahlen | erbracht: „Heute", „Wartet auf Sie", „Zuletzt gelaufen" (5 Läufe), „Auffällig" (5 gescheiterte Läufe) |
| N2 | Nutzer ohne Verwaltungsrecht erhält 403 | erbracht: `alice` als `member` → 403 mit dem vereinbarten Satz; `tests/test_admin_page.py` |
| N3 | Angelegter Nutzer meldet sich an und sieht eigene Daten | erbracht: Nutzer `probe.nutzer` über die Seite angelegt, Anmeldung über Keycloak, Startkennwort geändert, Übersicht zeigt „Keine Kalenderquelle", „Nichts wartet auf Sie", „Noch kein Auftrag gelaufen" |
| N4 | Jede Änderung erzeugt eine Protokollzeile | erbracht: `verwaltung.nutzer_angelegt`, `verwaltung.rolle_gesetzt`, `verwaltung.zugang_gesetzt` |
| N5 | Testlauf grün | erbracht: 158 bestanden, 8 übersprungen |

Testnutzer `probe.nutzer` wurde nach der Prüfung wieder gelöscht (Keycloak und `app_user`); die
Protokollzeile bleibt.
