# P2.1 — Gmail angebunden

Datum: 2026-11-05.

## Was jetzt geht

Gmail ist als Anbieter `gmail` eingehängt. Der Weg ist **nicht** OAuth, sondern **IMAP mit
App-Kennwort** — die Zugangsdaten, die in `~/.hermes/.env` stehen, sind genau dafür gedacht
(`EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `EMAIL_IMAP_HOST`, `EMAIL_SMTP_HOST`).

| Teil | Umsetzung |
|---|---|
| Server | fest: `imap.gmail.com:993` (TLS), `smtp.gmail.com:587` (STARTTLS) |
| Anmeldung | Adresse plus App-Kennwort; das Kennwort liegt als Fernet-Chiffrat in `credential` |
| Einrichtung | Seite `/postfaecher` (Anbieter „Gmail (App-Kennwort)") oder `scripts/import_gmail.py` |
| Prüfung ohne App | `scripts/check_gmail.py` |

## Nachweise

### Anmeldung und Lesen

```
$ uv run python scripts/check_gmail.py
Adresse: emil.mazdarati@gmail.com
IMAP:    imap.gmail.com:993
Login:   OK, 23 Ordner
INBOX:   14 Nachrichten
Adapter: 5 Nachrichten gelesen
```

### Durch die Werkzeuge des Agenten

Morgenbriefing gegen das echte Postfach:

```
Routine morgenbriefing: Werkzeuge ['list_calendar', 'search_mail', 'read_mail']
… Die neuesten E-Mails sind Informationen zu OAuth-Clients und Google-Diensten.
```

Der Agent hat also über `search_mail` und `read_mail` im echten Gmail-Postfach gelesen.
`list_calendar` meldet weiterhin, dass der Kalender über IMAP nicht verfügbar ist.

### Tests

`tests/test_provider_wiring.py` prüft: Gmail nutzt die festen Google-Server, und ohne
App-Kennwort nennt der Fehler den Weg zum Kennwort. Gesamtbilanz: **151 Tests grün**
(mit GreenMail für die IMAP-Tests).

## Abweichung von der SPEC

Die SPEC (P2.1) sieht einen **OAuth-Verbindungsfluss** vor. Umgesetzt ist stattdessen
IMAP mit App-Kennwort. Gründe:

* App-Kennwörter sind für ein Einzelpostfach der kürzere, prüfbare Weg; der OAuth-Client
  hätte eine Google-Cloud-Anwendung mit Zustimmungsbildschirm gebraucht.
* Lesen, Suchen, Kennzeichnen, Ablegen und Entwürfe laufen alle über IMAP — es fehlt nichts
  Wesentliches für v1.

Was damit **nicht** geht: Google Kalender, Drive, Docs. Dafür wäre OAuth nötig. Der
Kalender läuft bis dahin über ICS (siehe `arbeitsseiten-results.md`).

## Offen

* Senden ist geprüft — siehe unten.
* App-Kennwörter setzen Zwei-Faktor-Anmeldung voraus und lassen sich bei Google jederzeit
  widerrufen.

## Senden — geprüft am 05.11.2026

Auf ausdrückliche Anweisung des Nutzers ging eine Nachricht an `frank.b.reis@gmail.com`:

```
Entwurf:  Drafts|1 an frank.b.reis@gmail.com
Gesendet: 05.11.2026 19:00:09
Im Ordner [Gmail]/Gesendet: 1 Nachricht(en) mit diesem Betreff
```

Gegenprobe im Postfach:

```
[Gmail]/Gesendet: 1 Nachricht(en)
  An:       frank.b.reis@gmail.com
  Von:      emilmazdarati@gmail.com
  Betreff:  Testnachricht des OfficeAssistant
  Datum:    Thu, 05 Nov 2026 10:00:06 -0800 (PST)
  Text:     Diese Nachricht hat der OfficeAssistant gesendet … Gesendet am 05.11.2026 19:00
Drafts: 0 Nachricht(en)
```

Der Entwurf ist also nach dem Senden aus `Drafts` verschwunden und liegt in „Gesendet" —
genau das tut `send_draft`.

**Empfang bestätigt** vom Nutzer am 05.11.2026: „die mail ist angekommen". Der Weg
Entwurf → SMTP → Posteingang beim Empfänger ist damit durchgehend belegt.

**Hinweis zur Freigabe:** Gesendet wurde auf direkte Anweisung des Nutzers im Gespräch, nicht
über die Freigabe-Seite. Im Regelbetrieb läuft `send_draft` weiter über `@approval` und den
Freigabe-Eingang.

Hilfsskripte: `scripts/send_test_mail.py` (senden), `scripts/check_sent_mail.py` (gegenprüfen).
