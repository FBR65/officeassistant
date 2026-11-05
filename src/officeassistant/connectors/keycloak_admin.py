"""Nutzer über die Verwaltungsschnittstelle von Keycloak anlegen.

Keycloak führt das Verzeichnis (LDAP/AD). Anlegen läuft deshalb über Keycloak und nicht
über eine eigene Tabelle: sonst gäbe es zwei Wahrheiten über dieselbe Person.

Das Verzeichnis ist im Verbund derzeit `READ_ONLY`. Keycloak legt neue Nutzer dann im
eigenen Bestand an; für ein schreibbares Verzeichnis muss der Verbund auf `WRITABLE`
gestellt werden (SPEC 2026-11-05, Abschnitt 5.1).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class KeycloakError(RuntimeError):
    """Keycloak hat abgelehnt oder ist nicht erreichbar."""


@dataclass(frozen=True, slots=True)
class NeuerNutzer:
    benutzername: str
    email: str
    anzeigename: str
    passwort: str


def server_aus_issuer(issuer: str) -> str:
    """Aus `…/realms/oa` wird `…`; die Verwaltungsschnittstelle liegt neben den Realms."""
    basis = issuer.rstrip("/")
    if "/realms/" in basis:
        return basis.split("/realms/", 1)[0]
    return basis


class KeycloakAdmin:
    """Legt Nutzer über die Verwaltungsschnittstelle an.

    Der Administrator gehört zum Realm `master`; die Nutzer gehören zum Ziel-Realm.
    """

    def __init__(
        self,
        issuer: str,
        realm: str,
        benutzer: str,
        passwort: str,
        admin_realm: str = "master",
        timeout: float = 20.0,
    ) -> None:
        self._server = server_aus_issuer(issuer)
        self._realm = realm
        self._admin_realm = admin_realm
        self._benutzer = benutzer
        self._passwort = passwort
        self._timeout = timeout

    # -- Zugang ---------------------------------------------------------
    def _token(self) -> str:
        if not self._benutzer or not self._passwort:
            raise KeycloakError(
                "Für die Nutzerverwaltung fehlt ein Dienstkonto. Setzen Sie "
                "OA_KEYCLOAK_ADMIN_USER und OA_KEYCLOAK_ADMIN_PASSWORD."
            )
        try:
            antwort = httpx.post(
                f"{self._server}/realms/{self._admin_realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": self._benutzer,
                    "password": self._passwort,
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as fehler:
            raise KeycloakError(f"Keycloak nicht erreichbar: {fehler}") from fehler
        if antwort.status_code != 200:
            raise KeycloakError(
                "Keycloak hat das Dienstkonto abgelehnt. Prüfen Sie Benutzer und Kennwort."
            )
        return str(antwort.json()["access_token"])

    # -- Nutzer ---------------------------------------------------------
    def create_user(self, nutzer: NeuerNutzer) -> str:
        """Legt den Nutzer an und gibt seine Keycloak-Kennung zurück."""
        kopf = {"Authorization": f"Bearer {self._token()}"}
        rumpf = {
            "username": nutzer.benutzername,
            "email": nutzer.email,
            "firstName": nutzer.anzeigename.split(" ")[0] if nutzer.anzeigename else "",
            "lastName": " ".join(nutzer.anzeigename.split(" ")[1:]) if nutzer.anzeigename else "",
            "enabled": True,
            "emailVerified": True,
            "credentials": [
                {"type": "password", "value": nutzer.passwort, "temporary": True}
            ],
        }
        adresse = f"{self._server}/admin/realms/{self._realm}/users"
        try:
            antwort = httpx.post(adresse, json=rumpf, headers=kopf, timeout=self._timeout)
        except httpx.HTTPError as fehler:
            raise KeycloakError(f"Keycloak nicht erreichbar: {fehler}") from fehler

        if antwort.status_code == 409:
            raise KeycloakError(
                "Der Anmeldename ist bereits vergeben: " + nutzer.benutzername
            )
        if antwort.status_code not in (201, 204):
            raise KeycloakError(
                f"Keycloak hat den Nutzer abgelehnt (Status {antwort.status_code}): "
                f"{_grund(antwort)}"
            )

        # Keycloak nennt die Kennung im Kopf „Location"; sonst nachschlagen.
        ort = antwort.headers.get("Location", "")
        if ort:
            return ort.rsplit("/", 1)[-1]
        return self._find_id(nutzer.benutzername, kopf)

    def _find_id(self, benutzername: str, kopf: dict[str, str]) -> str:
        adresse = f"{self._server}/admin/realms/{self._realm}/users"
        antwort = httpx.get(
            adresse,
            params={"username": benutzername, "exact": "true"},
            headers=kopf,
            timeout=self._timeout,
        )
        treffer = antwort.json() if antwort.status_code == 200 else []
        if not treffer:
            raise KeycloakError(
                "Nutzer wurde angelegt, ist aber nicht zu finden: " + benutzername
            )
        return str(treffer[0]["id"])


def _grund(antwort: httpx.Response) -> str:
    try:
        daten = antwort.json()
    except ValueError:
        return antwort.text[:200]
    if isinstance(daten, dict) and daten.get("errorMessage"):
        return str(daten["errorMessage"])
    return antwort.text[:200]
