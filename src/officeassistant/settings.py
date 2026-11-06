"""Konfiguration des OfficeAssistant.

Grundsatz: jeder Pflichtwert kommt aus der Umgebung. Fehlt ein Wert, bricht der Start
mit einer deutschen Meldung ab, die den Variablennamen nennt. Stille Standardwerte
gibt es nur dort, wo sie im Betrieb unschädlich sind (Ports, API-Schlüssel-Platzhalter).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "OA_"


class SettingsError(RuntimeError):
    """Ungültige oder unvollständige Konfiguration."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    # Modellzugriff: ein OpenAI-kompatibler Endpunkt (llama-swap)
    model_base_url: str = Field(min_length=1)
    model_api_key: str = "none"
    role_leader: str = Field(min_length=1)
    role_drafting: str = Field(min_length=1)
    role_triage: str = Field(min_length=1)

    # Datenhaltung
    db_url: str = Field(min_length=1)

    # Verschlüsselung der Postfach-Token
    token_key: str = Field(min_length=1)

    # Identität (Keycloak vor LDAP/AD)
    oidc_issuer: str = Field(min_length=1)
    oidc_client_id: str = Field(min_length=1)
    oidc_client_secret: str = Field(min_length=1)
    oidc_redirect_url: str = "http://127.0.0.1:8099/auth/callback"

    # Nutzerverwaltung über die Keycloak-Verwaltungsschnittstelle
    keycloak_realm: str = "oa"
    keycloak_admin_user: str = ""
    keycloak_admin_password: str = ""

    # Oberfläche und API
    ui_host: str = "127.0.0.1"
    ui_port: int = 8099
    ui_base_url: str = "http://127.0.0.1:8099"
    api_base_url: str = "http://127.0.0.1:7777"
    kolibri_dir: str = "assets/kolibri"

    # Ablage für erzeugte Dateien und die zentrale Designvorlage für Präsentationen
    data_dir: str = "data"
    presentation_template: str = ""

    # Texterkennung für hochgeladene Dokumente (OpenAI-kompatibler Endpunkt)
    ocr_base_url: str = "http://127.0.0.1:8080/v1"
    ocr_model: str = "paddleocr-vl"
    ocr_api_key: str = ""
    ocr_timeout_s: float = 180.0
    ocr_dpi: int = 200
    ocr_min_textlayer: int = 40
    max_upload_bytes: int = 20 * 1024 * 1024
    agent_id: str = "office-assistant"
    approver_token: str = ""

    @classmethod
    def load(cls, **overrides: Any) -> "Settings":
        try:
            settings = cls(**overrides)
        except ValidationError as exc:
            raise SettingsError(_german_message(exc)) from exc
        _check_fernet_key(settings.token_key)
        return settings


def _missing_environment(exc: ValidationError) -> list[str]:
    missing: list[str] = []
    for error in exc.errors():
        if error["type"] in {"missing", "string_too_short"}:
            field = str(error["loc"][0]).upper()
            missing.append(f"{ENV_PREFIX}{field}")
    return missing


def _german_message(exc: ValidationError) -> str:
    missing = _missing_environment(exc)
    if missing:
        return "Fehlende Konfiguration: " + ", ".join(missing) + " fehlt."
    details = "; ".join(
        f"{ENV_PREFIX}{str(error['loc'][0]).upper()}: {error['msg']}"
        for error in exc.errors()
    )
    return "Ungültige Konfiguration: " + details


def _check_fernet_key(token_key: str) -> None:
    try:
        Fernet(token_key)
    except (ValueError, TypeError) as exc:
        raise SettingsError(
            "Ungültige Konfiguration: OA_TOKEN_KEY ist kein gültiger Fernet-Schlüssel. "
            'Erzeugen mit: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        ) from exc


def check_kolibri_dir(path: Path) -> None:
    """Die Oberfläche braucht die lokalen KoliBri-Dateien; ein CDN kommt nicht in Frage."""
    if not (path / "components" / "index.js").is_file():
        raise SettingsError(
            f"KoliBri-Assets fehlen unter {path}. Einbinden mit: "
            "npm ci --prefix assets && bash scripts/vendor_kolibri.sh"
        )
