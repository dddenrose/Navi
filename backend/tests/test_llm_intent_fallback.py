"""LLM 意圖分類 fallback 對模型輸出的防呆."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services import agent_service


def _llm_returning(result: agent_service._IntentResult) -> MagicMock:
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=result)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.parametrize("raw", ["null", "None", "  ", None])
async def test_textual_null_ticker_becomes_none(raw):
    # Gemini 3 把「沒有 ticker」輸出成字串 "null"，不是 JSON null
    result = agent_service._IntentResult(intent="entry_analysis", ticker=raw, confidence=0.9)

    classified = await agent_service._llm_classify_intent("這支值得買嗎", _llm_returning(result))

    assert classified == ("entry_analysis", None, 0.9)


async def test_real_ticker_passes_through():
    result = agent_service._IntentResult(intent="entry_analysis", ticker="聯發科", confidence=0.95)

    classified = await agent_service._llm_classify_intent("聯發科值得買嗎", _llm_returning(result))

    assert classified == ("entry_analysis", "聯發科", 0.95)
