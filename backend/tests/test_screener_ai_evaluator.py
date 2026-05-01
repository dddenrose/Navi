"""Tests for Stage 3 AI evaluator — LLM call fully mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from services.screener.ai_evaluator import EvaluatedPick, evaluate_candidates
from services.screener.factor_scorer import ScoredStock, StockFactors
from services.screener.prompts import ScreenerEvaluation


def _make_scored(ticker: str = "2330.TW") -> ScoredStock:
    f = StockFactors(ticker=ticker, name="台積電", industry="半導體", price=600)
    return ScoredStock(factors=f, factor_scores={"value": 60}, final_score=72.5)


def _fake_eval(confidence: int) -> ScreenerEvaluation:
    return ScreenerEvaluation(
        thesis="testing thesis",
        kb_citations=["valuation_methods.md"],
        target_price={"low": 600, "mid": 700, "high": 800},
        upside_pct=16.7,
        stop_loss=550,
        risk_reward_ratio=2.0,
        risks=["風險A", "風險B"],
        confidence=confidence,
    )


@pytest.mark.asyncio
@patch("services.screener.ai_evaluator._kb_context", return_value=("KB excerpt text", ["valuation_methods.md"]))
@patch("services.screener.ai_evaluator._build_llm")
async def test_evaluate_candidates_filters_by_confidence(mock_build_llm, _kb):
    """Picks below threshold should be dropped."""
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=[_fake_eval(85), _fake_eval(50)])
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    mock_build_llm.return_value = llm

    candidates = [_make_scored("2330.TW"), _make_scored("2317.TW")]
    out = await evaluate_candidates(
        candidates, profile="momentum", confidence_threshold=70
    )
    assert len(out) == 1
    assert out[0].evaluation.confidence == 85
    assert out[0].scored.factors.ticker == "2330.TW"


@pytest.mark.asyncio
@patch("services.screener.ai_evaluator._kb_context", return_value=("", []))
@patch("services.screener.ai_evaluator._build_llm")
async def test_evaluate_candidates_swallows_llm_errors(mock_build_llm, _kb):
    """LLM failures on individual picks should not crash the batch."""
    structured = MagicMock()
    structured.ainvoke = AsyncMock(
        side_effect=[RuntimeError("quota"), _fake_eval(80)]
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    mock_build_llm.return_value = llm

    out = await evaluate_candidates(
        [_make_scored("A"), _make_scored("B")],
        profile="value",
        confidence_threshold=0,
    )
    # the failing one is dropped
    assert len(out) == 1
    assert out[0].scored.factors.ticker == "B"
