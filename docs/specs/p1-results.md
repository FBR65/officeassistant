# P1 Ergebnisse

Datum: 2026-11-05
Projekt: `/home/speedy/Dokumente/dev/OfficeAssistant`
Regel: ein Punkt gilt als erledigt, wenn der Nachweis unten steht.

## Gesamtstand

| Task | Stand | Nachweis |
|---|---|---|
| P1.1 Abhängigkeiten | erledigt | `uv sync` sauber; `uv.lock` vorhanden |
| P1.2 Konfiguration | erledigt | 5 Tests; fehlende Variable nennt sich in Deutsch |
| P1.3 Anbieter-Vertrag + Fake | erledigt | 6 Tests; `FakeProvider` erfüllt `MailProvider` |
| P1.4 Schema + Migration | erledigt | idempotent, Version 1 |
| P1.5 Nutzer + Rollen | erledigt | Mitglied darf fremde Daten nicht lesen |
| P1.6 Token-Speicher | erledigt | Rundlauf; falscher Schlüssel → deutsche Meldung |
| P1.7 Protokoll | erledigt | Reihenfolge; `UPDATE` wird vom Trigger abgewiesen |
| P1.8 AgentOS mit Auth | erledigt | `/health` 200, `/agents` 401 ohne Token, 200 mit Token |
| P1.9 Oberfläche | **teilweise** | Anmeldeseite und Weiterleitung zu Keycloak geprüft; Ende-zu-Ende-Anmeldung nicht (kein Passwort durch den Agenten) |
| P1.10 Podman | erledigt | Abbild gebaut (651 MB), Container läuft, Endpunkte antworten |

Testsuite: **23 Tests, alle grün** (`uv run pytest` mit `OA_TEST_DB_URL`).

```
$ OA_TEST_DB_URL=postgresql://oa:oa@127.0.0.1:55432/oa uv run pytest
.......................                                                  [100%]
23 passed in 0.72s
```

## Einzelbefunde

### Konfiguration (P1.2)

Pflichtwerte kommen aus der Umgebung oder `.env`. Fehlt einer, lautet die Meldung
`Fehlende Konfiguration: OA_DB_URL fehlt.` — der Variablenname steht darin. Ein
ungültiger `OA_TOKEN_KEY` wird ebenfalls abgewiesen:

```
Ungültige Konfiguration: OA_TOKEN_KEY ist kein gültiger Fernet-Schlüssel.
```

### Datenhaltung (P1.4–P1.7)

Schema in `src/officeassistant/store/schema.sql`: `app_user`, `mail_account`,
`credential`, `task`, `routine`, `memory_entry`, `audit`. Migration ist idempotent
(zweimal ausgeführt, Version bleibt 1).

Das Protokoll ist technisch anhängend, nicht nur per Konvention:

```
UPDATE audit SET result_code = 'manipuliert' WHERE id = 1
→ psycopg.errors.RaiseException: audit is append-only
```

Zugangsdaten liegen je `(Nutzer, Postfach)` verschlüsselt; mit einem anderen Schlüssel
schlägt das Lesen fehl und nennt den Grund:

```
Zugangsdaten für Konto 1 nicht entschlüsselbar (falscher OA_TOKEN_KEY?)
```

### AgentOS-Backend (P1.8)

```
health: 200
agents ohne Token: 401
agents mit Mitglieds-Token: 200
```

Abweichung von der Spezifikation: `AuthorizationConfig` ist in Agno 3.1.12 abgekündigt
und reichte die JWKS-Datei nicht an den Prüfer durch. Richtig ist
`Authorization(jwks_file=…, algorithm="RS256")` aus `agno.os.authz`, übergeben als
`authorization=`. Damit entfällt die Umgebungsvariable `JWT_JWKS_FILE` (sie wird nur
noch für den Pfad gelesen).

Beim Start erscheint weiterhin eine Warnung über den RSA-OAEP-Schlüssel im JWKS. Das ist
der Verschlüsselungsschlüssel von Keycloak, kein Fehler; die Signaturprüfung nutzt den
RS256-Schlüssel.

### Oberfläche (P1.9)

Ohne Sitzung zeigt die Seite eine KoliBri-Karte „Anmeldung erforderlich" mit dem Knopf
„Anmelden". Der Knopf führt zu Keycloak:

```
GET /login → 302
Location: http://127.0.0.1:8180/realms/oa/protocol/openid-connect/auth
          ?response_type=code&client_id=oa-ui
          &redirect_uri=http%3A%2F%2F127.0.0.1%3A8099%2Fauth%2Fcallback
          &scope=openid+email+profile&state=…
```

Im Browser erscheint danach das Keycloak-Anmeldeformular (Felder `username`,
`password`). **Hier wurde abgebrochen:** der Agent gibt keine Passwörter ein. Damit ist
die Kette bis zum Formular belegt, der Rücksprung mit Sitzung und die Abmeldung nicht.
Vier Tests decken die Sitzungslogik ab (keine Sitzung → keine Identität, Sitzung →
Identität, abgelaufene Identität, Routen registriert).

Zum Schließen der Lücke: einmal im Browser als Testnutzer anmelden, oder das
Testpasswort in den Browser-Tresor legen und die Prüfung freigeben.

### Podman (P1.10)

`podman build --format docker -f deploy/api.containerfile` baut ein 651-MB-Abbild. Der
Container startet mit denselben Umgebungsvariablen und antwortet wie erwartet (`/health`
200, `/agents` 401).

Gesundheitsprüfung, nachgemessen:

```
podman inspect oa-api-hc --format '{{.State.Status}} health={{.State.Health.Status}}'
→ running health=healthy
```

Dafür ist `--format docker` nötig. Ohne den Schalter meldet der Bau
`HEALTHCHECK is not supported for OCI image format and will be ignored`; der Healthcheck
fehlt dann im Container. Beides steht jetzt in `deploy/README.md`. Die Quadlets setzen
`HealthCmd` zusätzlich.

Zwei Fehlversuche auf dem Weg, beide behoben:

| Fehler | Ursache | Lösung |
|---|---|---|
| `reading manifest 0.9 in docker.io/astral-sh/uv: requested access denied` | Bühnenabbild `astral-sh/uv:0.9` existiert nicht | `pip install uv==0.12.5` im Python-Abbild |
| `[Errno 98] address already in use` beim Containerstart | lokaler Testserver hielt Port 7777 | lokalen Server vorher beenden |

Nicht gebaut wurde das UI-Abbild (Node-Stufe für die KoliBri-Assets); der Bauplan liegt
in `deploy/ui.containerfile`.

## Offene Punkte aus P1

1. Ende-zu-Ende-Anmeldung mit echtem Nutzer (siehe P1.9).
2. UI-Abbild bauen und starten.
3. Quadlets im Benutzerkontext installieren (`deploy/README.md`, Abschnitt 5) — bisher
   nur mit losen Containern geprüft.
