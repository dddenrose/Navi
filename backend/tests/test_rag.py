"""Tests for Agent service (formerly RAG service)."""

import os

import pytest

_requires_gcp = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="GCP credentials not configured",
)


@_requires_gcp
@pytest.mark.asyncio
async def test_analyze_rsi_question():
    """Ask about RSI and expect a non-empty, knowledge-grounded response."""
    from services.agent_service import run_agent

    chunks = []
    async for chunk in run_agent("什麼是 RSI？何時該使用？"):
        if isinstance(chunk, str):
            chunks.append(chunk)

    full_response = "".join(chunks)
    assert len(full_response) > 50, "Response should be substantial"
    assert "RSI" in full_response


def test_intent_classifier():
    """Rule-based intent classifier should correctly classify common queries."""
    from services.agent_service import _classify_intent

    # Entry analysis
    intent, ticker, _ = _classify_intent("台積電可以買嗎？")
    assert intent == "entry_analysis"
    assert ticker == "台積電"

    # Technical analysis
    intent, ticker, _ = _classify_intent("2330的RSI是多少？")
    assert intent == "technical_analysis"
    assert ticker == "2330"

    # General
    intent, ticker, _ = _classify_intent("你好")
    assert intent == "general"
    assert ticker is None

    # Comprehensive
    intent, ticker, _ = _classify_intent("幫我分析鴻海")
    assert intent == "comprehensive_analysis"
    assert ticker == "鴻海"

    # News
    intent, _, _ = _classify_intent("最近有什麼新聞")
    assert intent == "news"

    # Portfolio
    intent, _, _ = _classify_intent("我的持股表現如何")
    assert intent == "portfolio"

    # Backtest
    intent, _, _ = _classify_intent("台積電均線交叉回測")
    assert intent == "backtest"


def test_intent_classifier_confidence_tiers():
    """High-signal patterns should return high confidence; unknown → low."""
    from services.agent_service import _classify_intent

    # Well-known pattern: backtest has 0.95 confidence
    _, _, conf = _classify_intent("台積電回測")
    assert conf >= 0.9

    # Ambiguous / no pattern match: confidence should be low enough to
    # trigger the LLM fallback in hybrid mode.
    _, _, conf = _classify_intent("隨便聊聊一些有的沒的")
    assert conf < 0.5


def test_intent_classifier_ticker_edge_cases():
    """Ticker extraction should avoid false positives on common acronyms."""
    from services.agent_service import _extract_ticker

    # Common acronyms should NOT be treated as tickers
    assert _extract_ticker("AI 產業怎麼看？") != "AI"
    assert _extract_ticker("什麼是 RSI") != "RSI"

    # TW numeric codes should match
    assert _extract_ticker("2330 的股價") == "2330"
    assert _extract_ticker("2330.TW 走勢") == "2330.TW"

    # Chinese company name before tech indicator
    assert _extract_ticker("台積電 MACD 怎麼樣") == "台積電"


@pytest.mark.asyncio
async def test_hybrid_classifier_regex_shortcut():
    """High-confidence regex match should NOT trigger the LLM fallback."""
    from services.agent_service import _classify_intent_hybrid

    # llm arg is unused on the regex fast path; pass None to detect
    # accidental LLM calls (would raise).
    intent, ticker, conf = await _classify_intent_hybrid("台積電回測", llm=None)  # type: ignore[arg-type]
    assert intent == "backtest"
    assert ticker == "台積電"
    assert conf >= 0.9
