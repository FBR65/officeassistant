"""P0.2 — approval durability across a process restart (Postgres backend).

The gated tool appends one line to executed.log. That file is the only proof
that the run really resumed and executed, not just that an API answered 200.

Run: uv run uvicorn spikes.p0_2_approval.app:app --port 7788
"""

from __future__ import annotations

from pathlib import Path

from agno.agent import Agent
from agno.approval import approval
from agno.db.postgres import PostgresDb
from agno.models.openai.like import OpenAILike
from agno.os import AgentOS
from agno.tools import tool

HERE = Path(__file__).parent
EXECUTED = HERE / "executed.log"

db = PostgresDb(db_url="postgresql+psycopg://oa:oa@127.0.0.1:55432/oa")


@approval
@tool(requires_confirmation=True)
def archive_message(message_id: str) -> str:
    """Archive one email message by its provider id."""
    with EXECUTED.open("a", encoding="utf-8") as fh:
        fh.write(f"archived {message_id}\n")
    return f"archived {message_id}"


agent = Agent(
    id="p02-agent",
    name="P0.2 Approval Agent",
    model=OpenAILike(
        id="deepseek-v4-pro-qwen3.5-9b",
        base_url="http://127.0.0.1:8080/v1",
        api_key="none",
    ),
    tools=[archive_message],
    instructions=[
        "Du bist ein Postfach-Assistent.",
        "Wenn der Nutzer bittet, eine Mail zu archivieren, rufe archive_message auf.",
        "Antworte danach kurz auf Deutsch.",
    ],
    db=db,
    add_history_to_context=True,
)

agent_os = AgentOS(
    id="p02",
    agents=[agent],
    db=db,
    scheduler=False,
)
app = agent_os.get_app()
