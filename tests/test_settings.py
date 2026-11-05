from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from officeassistant.settings import Settings, SettingsError

COMPLETE = {
    "OA_MODEL_BASE_URL": "http://127.0.0.1:8080/v1",
    "OA_DB_URL": "postgresql://oa:oa@127.0.0.1:5432/oa",
    "OA_TOKEN_KEY": Fernet.generate_key().decode(),
    "OA_OIDC_ISSUER": "http://127.0.0.1:8180/realms/oa",
    "OA_OIDC_CLIENT_ID": "oa-ui",
    "OA_OIDC_CLIENT_SECRET": "secret",
    "OA_ROLE_LEADER": "deepseek-v4-pro-qwen3.5-9b",
    "OA_ROLE_DRAFTING": "deepseek-v4-pro-qwen3.5-9b",
    "OA_ROLE_TRIAGE": "deepseek-v4-pro-qwen3.5-9b",
}


def test_load_reads_complete_environment(monkeypatch):
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)

    settings = Settings.load(_env_file=None)

    assert settings.db_url == COMPLETE["OA_DB_URL"]
    assert settings.model_base_url == COMPLETE["OA_MODEL_BASE_URL"]
    assert settings.role_leader == COMPLETE["OA_ROLE_LEADER"]


def test_defaults_are_explicit_not_silent(monkeypatch):
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)

    settings = Settings.load(_env_file=None)

    assert settings.model_api_key == "none"
    assert settings.ui_port == 8099
    assert settings.api_base_url == "http://127.0.0.1:7777"


def test_missing_variable_names_the_variable_in_german(monkeypatch):
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OA_DB_URL")

    with pytest.raises(SettingsError) as err:
        Settings.load(_env_file=None)

    assert "OA_DB_URL" in str(err.value)
    assert "fehlt" in str(err.value)


def test_missing_model_role_is_reported(monkeypatch):
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OA_ROLE_TRIAGE")

    with pytest.raises(SettingsError) as err:
        Settings.load(_env_file=None)

    assert "OA_ROLE_TRIAGE" in str(err.value)


def test_invalid_fernet_key_is_rejected(monkeypatch):
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("OA_TOKEN_KEY", "not-a-fernet-key")

    with pytest.raises(SettingsError) as err:
        Settings.load(_env_file=None)

    assert "OA_TOKEN_KEY" in str(err.value)
