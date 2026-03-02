"""Tests for agent_service — LangChain Tool-calling Agent."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Skip this module if heavy ML/GCP dependencies are not installed
try:
    import services.agent_service  # noqa: F401 — needed for patch() resolution

    HAS_DEPS = True
except (ImportError, Exception):
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(
    not HAS_DEPS,
    reason="LangChain/Vertex AI dependencies not installed",
)


# ── run_agent ─────────────────────────────────────────────────────────────────


class TestRunAgent:
    @pytest.mark.asyncio
    @patch("services.agent_service._build_llm")
    @patch("services.agent_service.create_tool_calling_agent")
    @patch("services.agent_service.AgentExecutor")
    async def test_streams_text_chunks(
        self, mock_executor_cls, mock_create_agent, mock_build_llm
    ):
        """run_agent should yield text chunks from the agent's final response."""
        mock_llm = MagicMock()
        mock_build_llm.return_value = mock_llm

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        # Simulate astream_events yielding on_chat_model_stream events
        async def fake_astream_events(inputs, version):
            for text in ["台積電", "目前", "偏多"]:
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": MagicMock(content=text)},
                }

        mock_executor = MagicMock()
        mock_executor.astream_events = fake_astream_events
        mock_executor_cls.return_value = mock_executor

        from services.agent_service import run_agent

        chunks = []
        async for chunk in run_agent("分析台積電"):
            chunks.append(chunk)

        assert chunks == ["台積電", "目前", "偏多"]

    @pytest.mark.asyncio
    @patch("services.agent_service._build_llm")
    @patch("services.agent_service.create_tool_calling_agent")
    @patch("services.agent_service.AgentExecutor")
    async def test_fallback_when_no_stream_events(
        self, mock_executor_cls, mock_create_agent, mock_build_llm
    ):
        """When no on_chat_model_stream events fire, fallback to ainvoke."""
        mock_build_llm.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        # astream_events yields no matching events
        async def fake_astream_events(inputs, version):
            yield {"event": "on_tool_start", "data": {}}

        mock_executor = MagicMock()
        mock_executor.astream_events = fake_astream_events
        mock_executor.ainvoke = AsyncMock(return_value={"output": "fallback response"})
        mock_executor_cls.return_value = mock_executor

        from services.agent_service import run_agent

        chunks = []
        async for chunk in run_agent("test question"):
            chunks.append(chunk)

        assert "".join(chunks) == "fallback response"

    @pytest.mark.asyncio
    @patch("services.agent_service._build_llm")
    @patch("services.agent_service.create_tool_calling_agent")
    @patch("services.agent_service.AgentExecutor")
    async def test_yields_error_message_on_exception(
        self, mock_executor_cls, mock_create_agent, mock_build_llm
    ):
        """run_agent should yield a friendly error message when an exception occurs."""
        mock_build_llm.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        async def failing_astream_events(inputs, version):
            raise RuntimeError("LLM unavailable")

        mock_executor = MagicMock()
        mock_executor.astream_events = failing_astream_events
        mock_executor_cls.return_value = mock_executor

        from services.agent_service import run_agent

        chunks = []
        async for chunk in run_agent("test"):
            chunks.append(chunk)

        full = "".join(chunks)
        assert "錯誤" in full or "抱歉" in full

    @pytest.mark.asyncio
    @patch("services.agent_service._build_llm")
    @patch("services.agent_service.create_tool_calling_agent")
    @patch("services.agent_service.AgentExecutor")
    @patch("services.agent_service.load_history")
    @patch("services.agent_service.save_history")
    async def test_loads_and_saves_conversation_history(
        self,
        mock_save,
        mock_load,
        mock_executor_cls,
        mock_create_agent,
        mock_build_llm,
    ):
        """When a conversation_id is supplied, history is loaded and saved."""
        mock_build_llm.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()
        mock_load.return_value = []

        async def fake_astream_events(inputs, version):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": MagicMock(content="回應")},
            }

        mock_executor = MagicMock()
        mock_executor.astream_events = fake_astream_events
        mock_executor_cls.return_value = mock_executor

        from services.agent_service import run_agent

        chunks = []
        async for chunk in run_agent("問題", conversation_id="conv123"):
            chunks.append(chunk)

        mock_load.assert_called_once_with("conv123")
        mock_save.assert_called_once_with("conv123", "問題", "回應")


# ── run_agent_sync ────────────────────────────────────────────────────────────


class TestRunAgentSync:
    @pytest.mark.asyncio
    @patch("services.agent_service.run_agent")
    async def test_concatenates_chunks(self, mock_run_agent):
        """run_agent_sync should join all streamed chunks into one string."""

        async def fake_run_agent(question, conversation_id=None):
            for chunk in ["Hello", " ", "world"]:
                yield chunk

        mock_run_agent.side_effect = fake_run_agent

        from services.agent_service import run_agent_sync

        result = await run_agent_sync("hi")
        assert result == "Hello world"

