"""OIDC-Anmeldung gegen Keycloak.

Die Anwendung kennt das Verzeichnis nicht. Keycloak authentifiziert gegen LDAP (heute)
oder Active Directory (später); hier kommt nur ein OIDC-Identitätsobjekt an:
`sub`, `email`, `name`, `access_token`.

Die Token liegen **nicht** im Browser: das Sitzungscookie trägt nur eine zufällige
Kennung, die Token stehen verschlüsselt in der Tabelle `ui_session`. Ein Cookie mit drei
JWT wäre größer als die 4096-Byte-Grenze und würde verworfen.
"""

from __future__ import annotations

from urllib.parse import quote

import time
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from officeassistant.settings import Settings
from officeassistant.store.ui_sessions import SESSION_KEY, SessionStore

_LIFETIME = 8 * 3600


@dataclass(frozen=True, slots=True)
class Identity:
    subject: str
    email: str
    name: str
    access_token: str
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 30


def _session_secret(settings: Settings) -> str:
    """Sitzungsschlüssel aus dem Token-Schlüssel ableiten, damit es eine Quelle gibt."""
    return settings.token_key[:32]


def discover(settings: Settings) -> dict[str, Any]:
    """Metadaten des Ausstellers lesen; ein Fehler nennt die URL."""
    url = f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"OIDC-Aussteller nicht erreichbar: {url}") from exc
    return response.json()


def session_store(settings: Settings) -> SessionStore:
    return SessionStore(settings.db_url, settings.token_key)


def install(app: FastAPI, settings: Settings) -> None:
    """Sitzung, OAuth-Client und die drei Routen an die Anwendung hängen."""
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_secret(settings),
        https_only=False,
        same_site="lax",
    )

    metadata = discover(settings)
    oauth = OAuth()
    oauth.register(
        name="keycloak",
        server_metadata_url=metadata["issuer"].rstrip("/") + "/.well-known/openid-configuration",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )

    @app.get("/login")
    async def login(request: Request):
        # prompt=login erzwingt die Passwortabfrage, auch wenn Keycloak noch eine
        # Sitzung im Browser hält (z. B. nach dem Abmelden).
        extra = {"ui_locales": "de"}
        if request.query_params.get("prompt"):
            extra["prompt"] = request.query_params["prompt"]
        return await oauth.keycloak.authorize_redirect(
            request, settings.oidc_redirect_url, **extra
        )

    @app.get("/auth/callback")
    async def callback(request: Request):
        # Eine bereits verbrauchte Kennung (Seite neu geladen, zwei Tabs) führt bei Keycloak
        # zu `invalid_grant`. Das ist kein Serverfehler, sondern eine neue Anmeldung.
        try:
            token = await oauth.keycloak.authorize_access_token(request)
        except Exception:  # noqa: BLE001 - authlib meldet jeden Grund gleich
            return RedirectResponse(
                "/login?fehler=" + quote("Die Anmeldung ist abgelaufen. Bitte erneut anmelden."),
                status_code=303,
            )
        claims = token.get("userinfo") or {}
        if not claims.get("sub"):
            claims = oauth.keycloak.parse_id_token(token, nonce=None)

        tokens = {
            "access_token": str(token.get("access_token", "")),
            "refresh_token": str(token.get("refresh_token", "")),
            "id_token": str(token.get("id_token", "")),
            "expires_at": time.time() + int(token.get("expires_in", 300)),
        }
        sid = session_store(settings).create(
            subject=str(claims["sub"]),
            email=str(claims.get("email", "")),
            name=str(claims.get("name") or claims.get("preferred_username") or ""),
            tokens=tokens,
            expires_at=time.time() + _LIFETIME,
        )
        # Im Cookie steht nur die Kennung; die Token bleiben auf dem Server.
        request.session[SESSION_KEY] = sid
        return RedirectResponse("/")

    @app.get("/logout")
    async def logout(request: Request):
        sid = str(request.session.pop(SESSION_KEY, "") or "")
        store = session_store(settings)
        data = store.load(sid) if sid else None
        id_token = str(((data or {}).get("tokens") or {}).get("id_token", ""))
        if sid:
            store.delete(sid)

        end_session = metadata.get("end_session_endpoint")
        if end_session:
            params = {
                "post_logout_redirect_uri": settings.ui_base_url + "/",
                "client_id": settings.oidc_client_id,
            }
            if id_token:
                params["id_token_hint"] = id_token
            return RedirectResponse(end_session + "?" + urlencode(params))
        # Ohne Endpunkt bleibt nur, die nächste Anmeldung auf Passwort zu zwingen.
        return RedirectResponse("/login?prompt=login")


class NotAuthenticated(RuntimeError):
    """Keine gültige Sitzung; der Nutzer muss sich neu anmelden."""


def current_session(request: Request, settings: Settings) -> dict[str, Any] | None:
    """Serverseitige Sitzung lesen (Kennung steht im Cookie)."""
    if "session" not in request.scope:
        return None
    sid = str(request.session.get(SESSION_KEY, "") or "")
    if not sid:
        return None
    return session_store(settings).load(sid)


def identity(request: Request, settings: Settings) -> Identity | None:
    """Angemeldete Person, oder None."""
    data = current_session(request, settings)
    if data is None:
        return None
    tokens = data["tokens"]
    return Identity(
        subject=str(data["subject"]),
        email=str(data["email"]),
        name=str(data["name"]),
        access_token=str(tokens.get("access_token", "")),
        expires_at=float(tokens.get("expires_at", 0)),
    )


async def access_token(request: Request, settings: Settings) -> str:
    """Gültiges Zugangstoken liefern und es bei Bedarf erneuern.

    Keycloak-Token gelten 10 Minuten. Ohne Erneuerung antwortet die Agenten-API nach
    dieser Zeit mit 401, obwohl die Sitzung noch gilt.
    """
    data = current_session(request, settings)
    if data is None:
        raise NotAuthenticated("Keine Sitzung")

    sid = str(request.session.get(SESSION_KEY, "") or "")
    tokens = data["tokens"]
    if float(tokens.get("expires_at", 0)) > time.time() + 30:
        return str(tokens.get("access_token", ""))

    refresh_token = str(tokens.get("refresh_token", ""))
    if not refresh_token:
        raise NotAuthenticated("Sitzung abgelaufen")

    metadata = discover(settings)
    response = httpx.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise NotAuthenticated("Sitzung abgelaufen")

    fresh = response.json()
    tokens["access_token"] = str(fresh.get("access_token", ""))
    tokens["refresh_token"] = str(fresh.get("refresh_token", refresh_token))
    tokens["expires_at"] = time.time() + int(fresh.get("expires_in", 300))
    session_store(settings).update_tokens(sid, tokens, expires_at=time.time() + _LIFETIME)
    return str(tokens["access_token"])


def with_fresh_token(user: Identity, token: str) -> Identity:
    """Identität mit erneuertem Token."""
    return replace(user, access_token=token)
