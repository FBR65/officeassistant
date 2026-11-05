"""Freigaben und Läufe aufräumen, die aus der Testphase mit dem Testpostfach stammen.

Was bleibt: Freigaben zu echten Aktionen (Versand, Kennzeichnen). Was geht: Verweise auf
Entwürfe `d4`, `d5`, `d10` und der Testlauf `archive_message`, dazu Läufe, die nie
fortgesetzt wurden.
"""

from __future__ import annotations

import sys

from officeassistant.settings import Settings
from officeassistant.store import db

TEST_ENTWUERFE = ("d4", "d5", "d10")


def main() -> None:
    settings = Settings.load()
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        vorher = conn.execute("SELECT count(*) AS n FROM ai.agno_approvals").fetchone()["n"]

        # 1) Freigaben zu Entwürfen, die es im Postfach nie gab.
        entfernt = conn.execute(
            """
            DELETE FROM ai.agno_approvals
            WHERE tool_name = 'archive_message'
               OR tool_args->>'draft_id' = ANY(%s)
            """,
            (list(TEST_ENTWUERFE),),
        ).rowcount

        # 2) Läufe, die auf eine Freigabe warten, die längst entschieden ist.
        #    Erst nach dem Löschen prüfen: offen ist nur, was noch `pending` ist.
        steckend = conn.execute(
            """
            UPDATE ai.agno_runs SET status = 'CANCELLED'
            WHERE status = 'PAUSED'
              AND run_id NOT IN (
                SELECT run_id FROM ai.agno_approvals WHERE status = 'pending'
              )
            """
        ).rowcount

        nachher = conn.execute("SELECT count(*) AS n FROM ai.agno_approvals").fetchone()["n"]
        offen = conn.execute(
            "SELECT count(*) AS n FROM ai.agno_approvals WHERE status = 'pending'"
        ).fetchone()["n"]
        wartend = conn.execute(
            "SELECT count(*) AS n FROM ai.agno_runs WHERE status = 'PAUSED'"
        ).fetchone()["n"]

        print(f"Freigaben: {vorher} → {nachher} (entfernt {entfernt}, davon offen: {offen})")
        print(f"Läufe auf 'CANCELLED' gesetzt: {steckend}, noch wartend: {wartend}")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
