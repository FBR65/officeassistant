"""Vorführdaten anlegen: ein Nutzer mit einem Testpostfach (Anbieter `fake`).

Aufruf: uv run python scripts/seed_demo.py <nutzer-id> <email>
Die Nutzer-ID ist das `sub` aus dem JWT (Keycloak).
"""

from __future__ import annotations

import sys

from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.tokens import TokenStore
from officeassistant.store.users import UserStore


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    user_id, email = sys.argv[1], sys.argv[2]

    settings = Settings.load()
    conn = db.connect(settings.db_url)
    try:
        db.migrate(conn)
        user = UserStore(conn).upsert(user_id, email, email.split("@")[0])
        account = TokenStore(conn, settings.token_key).save(user_id, "fake", email, {})
        conn.commit()
        print(f"Nutzer {user.id} ({user.role}), Postfach {account.address} [{account.provider}]")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
