"""Tests for ai_evaluator — 數字幻覺零容忍：違規即重試，重試耗盡即 fallback。"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.screener import ai_evaluator
from services.screener.ai_evaluator import _interpret_one
from services.screener.factor_scorer import EvaluatedStock
from services.screener.prompts import StockInterpretation
from services.screener.rules import ScoringTrace, StockData


def _evaluated_stock() -> EvaluatedStock:
    data = StockData(
        ticker="9999.TW",
        name="Test",
        industry="X",
        price=100.0,
        pe=20.0,
    )
    return EvaluatedStock(data=data, trace=ScoringTrace(profile="momentum"))


def _interp(narrative: str) -> StockInterpretation:
    return StockInterpretation(narrative=narrative)


_CLEAN = "動能訊號顯示相對強勢，若量能不退潮，波段結構仍屬健康。"
_HALLUCINATED = "毛利率高達 45%，動能強勁。"  # 45% 不在白名單


async def test_single_violation_triggers_retry():
    """B3 迴歸：舊版容許 1 個違規數字直接出稿；現在任何違規都必須重試。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[_interp(_HALLUCINATED), _interp(_CLEAN)])
    with patch.object(ai_evaluator, "_RETRY_BASE_DELAY", 0):
        result = await _interpret_one(llm, _evaluated_stock(), "momentum")
    assert llm.ainvoke.await_count == 2
    assert result.interpretation.narrative == _CLEAN


async def test_persistent_violations_fall_back():
    """重試耗盡仍有違規 → 改用規則生成的保守版，未授權數字不得出稿。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[_interp(_HALLUCINATED)] * 3)
    with patch.object(ai_evaluator, "_RETRY_BASE_DELAY", 0):
        result = await _interpret_one(llm, _evaluated_stock(), "momentum")
    assert llm.ainvoke.await_count == 3
    assert "45%" not in result.interpretation.narrative
    assert "解讀" in result.interpretation.narrative  # fallback 文案


async def test_clean_output_accepted_first_try():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_interp(_CLEAN))
    with patch.object(ai_evaluator, "_RETRY_BASE_DELAY", 0):
        result = await _interpret_one(llm, _evaluated_stock(), "momentum")
    assert llm.ainvoke.await_count == 1
    assert result.interpretation.narrative == _CLEAN
