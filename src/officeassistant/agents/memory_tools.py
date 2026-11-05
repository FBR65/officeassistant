"""Werkzeug „merken" und die Anweisungen aus dem Gedächtnis (P4.7)."""

from __future__ import annotations

from agno.run import RunContext
from agno.tools import tool

from officeassistant.settings import Settings
from officeassistant.store import db, memory


@tool
def remember(fact: str, kind: str = "other", run_context: RunContext | None = None) -> dict:
    """Merkt sich einen Satz über den Nutzer, zum Beispiel eine Vorliebe oder einen Namen.

    Args:
        fact: Der Merksatz, kurz und als Aussage.
        kind: person, project, voice oder other.
    """
    if run_context is None or not getattr(run_context, "user_id", None):
        return {"fehler": "Kein angemeldeter Nutzer am Werkzeugaufruf."}
    if kind not in memory.KINDS:
        return {"fehler": "Unbekannte Art. Erlaubt: " + ", ".join(memory.KINDS)}

    nutzer = str(run_context.user_id)
    settings = Settings.load()
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        eintrag = memory.remember(conn, nutzer, fact, kind, source="chat")
    except ValueError as exc:
        return {"fehler": str(exc)}
    finally:
        conn.close()
    return {"gemerkt": eintrag.text, "art": eintrag.kind, "id": eintrag.id}


MEMORY_TOOLS = [remember]


def memory_instructions(run_context) -> list[str]:
    """Anweisungen für den Lauf: die Merksätze dieses Nutzers, sonst keine.

    Agno ruft dieses Objekt bei jedem Lauf auf und übergibt den Laufkontext.
    """
    user_id = getattr(run_context, "user_id", None)
    if not user_id:
        return []
    settings = Settings.load()
    conn = db.connect(settings.db_url, autocommit=True)
    try:
        return memory.as_instructions(conn, user_id)
    except Exception:  # noqa: BLE001 - ein fehlendes Gedächtnis darf keinen Lauf stoppen
        return []
    finally:
        conn.close()
