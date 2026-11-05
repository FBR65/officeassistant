"""Anwendungshülle (P1): Anmeldung, Abmeldung, deutsche Navigation, KoliBri.

Start: uv run officeassistant-ui   (oder uvicorn officeassistant.ui.app:app)
"""

from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from officeassistant.settings import Settings, check_kolibri_dir
from officeassistant.store import db
from officeassistant.ui import (
    accounts,
    admin_page,
    overview,
    activity_page,
    calendar_page,
    chat_page,
    approvals,
    connections_page,
    auth,
    layout,
    mail_page,
    memory_page,
    routines_page,
    runs,
)

SETTINGS = Settings.load()
ASSETS = Path(SETTINGS.kolibri_dir).resolve()
check_kolibri_dir(ASSETS)


def _migrate() -> int:
    """Schema anwenden. Ohne diesen Schritt fehlen neue Tabellen still."""
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        return db.migrate(conn)
    finally:
        conn.close()


SCHEMA_VERSION = _migrate()

app.add_static_files("/kolibri", str(ASSETS))
auth.install(app, SETTINGS)
accounts.register(app)
runs.register(app)
approvals.register(app)
routines_page.register(app)
memory_page.register(app)
connections_page.register(app)
calendar_page.register(app)
mail_page.register(app)
chat_page.register(app)
admin_page.register(app)



def main() -> None:
    ui.run(
        host=SETTINGS.ui_host,
        port=SETTINGS.ui_port,
        title="OfficeAssistant",
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
