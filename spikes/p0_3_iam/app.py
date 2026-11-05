"""P0.3 — Keycloak (LDAP-backed) JWT against AgentOS with authorization and isolation."""

from __future__ import annotations

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai.like import OpenAILike
from agno.os import AgentOS
from agno.os.config import AuthorizationConfig
from agno.tools import tool

db = PostgresDb(db_url="postgresql+psycopg://oa:oa@127.0.0.1:55432/oa")


@tool
def whoami(note: str = "") -> str:
    """Return a fixed marker so the test can see that a tool ran."""
    return f"ok:{note}"


agent = Agent(
    id="p03-agent",
    name="P0.3 Identity Agent",
    model=OpenAILike(
        id="deepseek-v4-pro-qwen3.5-9b",
        base_url="http://127.0.0.1:8080/v1",
        api_key="none",
    ),
    tools=[whoami],
    instructions=["Antworte auf Deutsch in einem Satz."],
    db=db,
)

agent_os = AgentOS(
    id="p03",
    agents=[agent],
    db=db,
    authorization=True,
    user_isolation=True,
    authorization_config=AuthorizationConfig(
        jwks_file="/tmp/oa_jwks.json",
        algorithm="RS256",
    ),
)
app = agent_os.get_app()
