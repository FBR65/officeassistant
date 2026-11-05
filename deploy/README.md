# Betrieb mit Podman (rootless Quadlets)

Alles läuft im Benutzerkontext. Keine Ports nach außen außer dem, den ein Reverse Proxy
freigibt; die Dienste selbst hören nur auf 127.0.0.1.

## 1. Verzeichnisse und Zugangsdaten

**Wichtig:** Der Realm-Export enthält aus Sicherheitsgründen **keine** Client-Secrets. Der
Platzhalter `BITTE-NACH-IMPORT-SETZEN` ist nach dem Import zu ersetzen:

```bash
podman exec oa-kc /opt/keycloak/bin/kcadm.sh set-password \
  --server http://localhost:8080 --realm master --user admin
# neues Client-Secret für oa-ui setzen (Konsole → Clients → oa-ui → Anmeldedaten)
```

Danach den Wert in `.env` als `OA_OIDC_CLIENT_SECRET` eintragen.

```bash
mkdir -p ~/officeassistant
podman network create oa            # oder die Quadlet-Datei oa.network verwenden
podman secret create pg-password -        # Passwort eingeben, Strg+D
podman secret create keycloak-admin-password -
podman secret create oidc-jwks.json /pfad/jwks.json
```

`oidc-jwks.json` ist die Schlüsseldatei des Ausstellers:

```bash
curl -fsS http://127.0.0.1:8180/realms/oa/protocol/openid-connect/certs \
  -o /pfad/jwks.json
```

Ohne diese Datei startet die API nicht. Fehlt das Python-Paket `cryptography`, lässt
sich kein RS256-Schlüssel lesen; es ist als Abhängigkeit fest eingetragen.

## 2. Konfigurationsdateien

`~/officeassistant/api.env` und `~/officeassistant/ui.env` nach `.env.example` anlegen.
Pflichtwerte: `OA_DB_URL`, `OA_TOKEN_KEY`, `OA_OIDC_ISSUER`, `OA_OIDC_CLIENT_ID`,
`OA_OIDC_CLIENT_SECRET`, `OA_ROLE_LEADER`, `OA_ROLE_DRAFTING`, `OA_ROLE_TRIAGE`.
Fehlt einer, bricht der Start mit einer deutschen Meldung ab, die den Variablennamen nennt.

## 3. Abbilder bauen

```bash
podman build --format docker -f deploy/api.containerfile -t localhost/oa-api:0.1 .
podman build --format docker -f deploy/ui.containerfile  -t localhost/oa-ui:0.1 .
```

`--format docker` ist nötig: im OCI-Format ignoriert Podman die `HEALTHCHECK`-Zeile
(Meldung: „HEALTHCHECK is not supported for OCI image format and will be ignored").
Die Quadlets setzen `HealthCmd` zusätzlich, damit der Zustand auch ohne diesen Schalter
sichtbar ist.

## 4. Keycloak einrichten

Realm-Vorlage: `deploy/realm-oa.json`. Sie enthält **auch die vier LDAP-Attribut-Mapper** —
ohne sie scheitert die Anmeldung mit `User returned from LDAP has null username`.
Vor dem Import ersetzen: `CHANGE-ME` (Bind-Passwort, Client-Secret) und die
`redirectUris` (eigene Adresse).

Beim späteren Wechsel auf Active Directory ändern sich nur:
Vendor-Preset `Active Directory`, Login-Attribut `sAMAccountName`/`userPrincipalName`,
Gruppenfilter. Anwendungscode bleibt unverändert.

## 5. Dienste starten

Vorher einmalig das Dienstkonto für Freigaben anlegen (Variante B):

```bash
export AGNO_ADMIN_TOKEN=<kurzlebiges Admin-JWT aus Keycloak>
uv run agno tokens create approver-admin --scopes agent_os:admin --privileged \
    --url http://127.0.0.1:7777 --json
# Token in OA_APPROVER_TOKEN der ui.env eintragen
```

Warum `agent_os:admin` und nicht nur `approvals:write`: Agno behandelt jedes
Dienstkonto als selbstbezogen und lässt es bei eingeschalteter Nutzertrennung keine
Freigaben auflösen — es sei denn, das Token trägt Admin-Rechte. Das Token gehört
deshalb ausschließlich in den Prozess der Oberfläche, nie in den Browser.

```bash
cp deploy/*.container deploy/oa.network ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start officeassistant-db officeassistant-api officeassistant-ui
systemctl --user status officeassistant-api
```

## 6. Prüfen

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7777/health   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7777/agents   # 401 ohne Token
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/         # 200
```

Rollen: `owner` und `admin` sind Ausnahmen und werden protokolliert. Ein Token mit
`agent_os:admin` umgeht die Nutzertrennung — Mitglieder erhalten nur enge Scopes
(`agents:read`, `agents:*:run`, `sessions:read`, `sessions:write`).

## 7. Sicherung

Datenbank: `podman exec officeassistant-db pg_dump -U oa oa > oa-$(date +%F).sql`.
Schlüssel `pg-password`, `keycloak-admin-password` und `OA_TOKEN_KEY` getrennt aufbewahren:
ohne `OA_TOKEN_KEY` sind die gespeicherten Postfach-Token nicht entschlüsselbar.
