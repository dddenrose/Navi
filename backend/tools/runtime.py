"""Per-request values the backend injects into tools — never chosen by the model.

Tools that act on the signed-in user declare a ``config: RunnableConfig`` parameter.
LangChain fills it from the caller and leaves it out of the schema the model sees,
so a prompt cannot point a tool at another user's data.
"""

from langchain_core.runnables import RunnableConfig


def user_config(user_id: str) -> RunnableConfig:
    """Build the config the agent runner passes when invoking tools."""
    return {"configurable": {"user_id": user_id}}


def user_id_from(config: RunnableConfig | None) -> str:
    """Read the uid injected by the agent runner; empty when there is none."""
    configurable = (config or {}).get("configurable") or {}
    return str(configurable.get("user_id") or "")
