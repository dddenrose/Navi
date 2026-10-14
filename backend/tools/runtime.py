"""Per-request values the backend injects into tools — never chosen by the model.

Tools that act on the signed-in user declare a ``config: RunnableConfig`` parameter.
LangChain fills it from the caller and leaves it out of the schema the model sees,
so a prompt cannot point a tool at another user's data.
"""

from langchain_core.runnables import RunnableConfig


def user_config(user_id: str, **context: str) -> RunnableConfig:
    """Build the config the agent runner passes when invoking tools.

    context 是呼叫端額外帶給工具的值，例如 LINE 的 line_user_id。
    """
    return {"configurable": {**context, "user_id": user_id}}


def _configurable(config: RunnableConfig | None) -> dict:
    return (config or {}).get("configurable") or {}


def user_id_from(config: RunnableConfig | None) -> str:
    """Read the uid injected by the agent runner; empty when there is none."""
    return str(_configurable(config).get("user_id") or "")


def line_user_id_from(config: RunnableConfig | None) -> str:
    """Read the LINE user ID injected by the LINE handler; empty outside LINE."""
    return str(_configurable(config).get("line_user_id") or "")
