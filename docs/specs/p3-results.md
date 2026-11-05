# P3 — Microsoft-Pfade und IMAP: Stand

Datum: 2026-11-05
Auftrag: SPEC-Abschnitt 7, Phase P3.

## Ergebnis in einer Zeile

P3.5 (IMAP/SMTP für Exchange on-prem) ist **fertig und gegen einen echten IMAP-Server
geprüft**. P3.6 ist **teilweise** fertig: Anbieterwahl je Postfach gibt es, der parallele
Betrieb mit Gmail ist offen, weil der Gmail-Anbieter selbst noch fehlt (P2.1).
P3.1–P3.4 (Microsoft Graph) sind **nicht begonnen** — es gibt kein Entra-Konto und keine
Zustimmung eines Tenants.

## Einzelne Punkte

| # | Aufgabe | Stand | Nachweis |
|---|---|---|---|
| P3.1 | Graph-Anmeldung (Device Code, Erneuerung, mehrere Konten) | nicht begonnen | kein Tenant, keine App-Registrierung |
| P3.2 | Graph-Suche / Nachricht lesen | nicht begonnen | — |
| P3.3 | Graph-Entwurf / Senden | nicht begonnen | — |
| P3.4 | Graph-Kalender lesen, Termin anlegen | nicht begonnen | — |
| P3.5 | `ImapAdapter` Suche, Lesen, Entwurf, Senden über IMAP/SMTP | **fertig** | 8 Tests gegen GreenMail, Agentenlauf gegen echtes Postfach |
| P3.6 | Anbieterwahl je Konto in der Oberfläche | teilweise | Auswahl `imap`/`fake` wirkt, Gmail fehlt |

## Was P3.5 kann

Datei: `src/officeassistant/providers/imap.py`

| Aufgabe | Umsetzung |
|---|---|
| Suche | Serverfilter nur nach Datum; Freitext wird im Client geprüft, weil IMAP-SEARCH Betreffs mit Umlauten als `=?utf-8?…?=` sieht und nie träfe. Findet der Kopf nichts, werden die Körper der jüngsten 25 Nachrichten geprüft. |
| Nachricht lesen | `RFC822` holen, Text- und HTML-Teil trennen, HTML über `providers/text.py` in Text wandeln. Kein HTML geht an das Modell. |
| Entwurf | `APPEND` in den Ordner `Drafts` mit Kennzeichen `\Draft`; Kennung über `APPENDUID`, sonst über `Message-ID`. |
| Senden | Nur über `send_draft`; die Nachricht wird per SMTP gesendet und danach nach `Sent` kopiert. |
| Label | IMAP kennt keine Labels: ein Label ist ein Ordner. Ordner wird bei Bedarf angelegt, Nachricht hineinkopiert. |
| Lesen/Ablegen/Löschen | `\Seen` setzen, nach `Archive` bzw. `Trash` verschieben, endgültig löschen mit `EXPUNGE`. |
| Kalender | `NotSupported` mit dem Hinweis, Exchange Online über Graph anzubinden. |

Nachrichten werden als `Ordner|UID` angesprochen, weil eine UID nur innerhalb eines
Ordners gilt.

## Nachweise

### Tests gegen einen echten Server

GreenMail im Container (`docker.io/greenmail/standalone`), Benutzer `alice`, `bob`.

```
podman run -d --rm --name oa-mail -p 3025:3025 -p 3143:3143 \
  -e GREENMAIL_OPTS="-Dgreenmail.setup.test.all \
     -Dgreenmail.users=alice:alicepw@example.org,bob:bobpw@example.org \
     -Dgreenmail.hostname=0.0.0.0" docker.io/greenmail/standalone:latest
OA_TEST_IMAP=1 uv run pytest tests/test_imap_provider.py -q     → 8 passed
```

Geprüft: Vertrag erfüllt (`isinstance(provider, MailProvider)`), Suche mit Umlaut,
Nachricht lesen ohne HTML, `\Seen` gesetzt, Label als Ordner angelegt, Entwurf erst nach
`send_draft` beim Empfänger, Archiv verschiebt aus dem Posteingang, Kalender meldet
`NotSupported`, fehlende Zugangsdaten werden benannt.

Beim Bau gefundene und behobene Fehler:

| Fehler | Ursache | Behebung |
|---|---|---|
| `Connection unexpectedly closed` beim Zustellen | GreenMail bindet auf `127.0.0.1` im Container, veröffentlichte Ports erreichen ihn nicht | `-Dgreenmail.hostname=0.0.0.0` |
| `ValueError: date_time must be aware` | `imaplib.Time2Internaldate` braucht eine Zeit mit Zeitzone | `datetime.now(UTC)` |
| `UnicodeEncodeError` bei „Statusprüfung" | `imaplib` kodiert Zeichenketten als ASCII | Suchbegriffe als Bytes |
| Suche fand Umlaute nicht | Server vergleicht Roh-Kopfzeilen, Betreff steht dort kodiert | Freitext im Client filtern |

### Lauf über den Agenten

Konto in der Oberfläche verbunden (`imap`, `127.0.0.1:3143`, Verschlüsselung „keine"),
dann ein Auftrag an `office-assistant`:

> Welche Mails liegen im Posteingang? Nenne Betreff und Absender.

Antwort des Laufs (`COMPLETED`), Auszug:

```
1. **Rechnung 4711** (INBOX|1)
2. **Statusprüfung** (INBOX|2)
3. **Etikettentest** (INBOX|3)
...
```

Das sind genau die Nachrichten, die die Tests zuvor an dieses Postfach geschickt hatten.
Der Weg Oberfläche → Werkzeug → IMAP → Modell ist damit belegt.

## Was die Oberfläche jetzt kann

`/postfaecher` hat neben der Adresse Felder für IMAP-Server, Port, Benutzername, Kennwort,
SMTP-Server, SMTP-Port und eine Auswahl der Verschlüsselung
(`TLS`, `ohne TLS beim Abholen`, `ohne Verschlüsselung`). Ohne Server, Benutzer und Kennwort
verweigert die Seite das Verbinden und nennt die fehlenden Felder.

Zugangsdaten liegen als Fernet-Chiffrat in `credential`; der Adapter bekommt sie
entschlüsselt aus `TokenStore`.

Nebenbei behoben: Navigations- und Abmeldeknöpfe trugen `onclick`-Attribute, die diese
Seite nicht ausführt. Sie tragen jetzt `data-href`; ein Zuhörer im Seitengerüst navigiert.

## Offen

* **P2.1** Gmail-Anbieter (OAuth-Client fehlt).
* **P3.1–P3.4** Graph: braucht eine App-Registrierung im Tenant und die Zustimmung eines
  Administrators.
* **P3.6** vollständig erst, wenn Gmail daneben läuft.
* Der Testcontainer `oa-mail` läuft noch; er ist nicht Teil des Betriebs.

## Testbilanz

`OA_TEST_IMAP=1 OA_TEST_DB_URL=… uv run pytest` → **67 passed in 14,19 s**.
