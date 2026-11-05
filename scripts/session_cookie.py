"""Sitzungscookie bauen (nur für lokale Prüfungen ohne Browser).

Die Token liegen serverseitig in `ui_session`; das Cookie trägt nur die Kennung.
Bildet das Format der Starlette-Session nach: base64(JSON) plus Zeitstempel-Signatur.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time

from itsdangerous import TimestampSigner

from officeassistant.settings import Settings
from officeassistant.store.ui_sessions import SESSION_KEY, SessionStore


def build(secret: str, session: dict) -> str:
    raw = base64.b64encode(json.dumps(session, separators=(",", ":")).encode("utf-8"))
    return TimestampSigner(str(secret)).sign(raw).decode("utf-8")


if __name__ == "__main__":
    settings = Settings.load()
    subject = sys.argv[1] if len(sys.argv) > 1 else "ae643b35-86f3-4745-9af8-7bb78b9fb3e9"
    email = sys.argv[2] if len(sys.argv) > 2 else "alice@example.org"
    token = os.environ.get("OA_SESSION_TOKEN", "")
    refresh = os.environ.get("OA_SESSION_REFRESH", "")
    expires_in = float(os.environ.get("OA_SESSION_EXPIRES_IN", "600"))

    sid = SessionStore(settings.db_url, settings.token_key).create(
        subject=subject,
        email=email,
        name="Alice",
        tokens={
            "access_token": token,
            "refresh_token": refresh,
            "id_token": "",
            "expires_at": time.time() + expires_in,
        },
        expires_at=time.time() + 8 * 3600,
    )
    print(build(settings.token_key[:32], {SESSION_KEY: sid}))
