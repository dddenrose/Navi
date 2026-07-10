"""Tests for screener factor_scorer — 殖利率正規化迴歸。"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.screener.factor_scorer import _build_stock_data
from services.screener.universe import UniverseRecord


def _record(info: dict) -> UniverseRecord:
    n = 30
    df = pd.DataFrame(
        {
            "Close": [100.0 + i * 0.1 for i in range(n)],
            "Volume": [1_000_000] * n,
        }
    )
    return UniverseRecord(
        ticker="2330.TW",
        name="台積電",
        industry="半導體",
        price=100.0,
        market_cap=1e12,
        avg_turnover_20d=1e8,
        history=df,
        info=info,
    )


class TestDividendYieldNormalization:
    """yfinance>=0.2.40 的 dividendYield 一律為百分比形式（0.8 表 0.8%）。

    迴歸：舊版 `>1` 啟發式會把殖利率 <1% 的股票放大 100 倍（0.8 → 80%），
    導致快照顯示荒謬數字且 VB4（門檻 2.5%）誤判通過。
    """

    def test_sub_one_percent_yield_not_inflated(self):
        data = _build_stock_data(
            _record({"dividendYield": 0.8}), benchmark_return_6m=None
        )
        assert data.dividend_yield == pytest.approx(0.008)

    def test_normal_yield(self):
        data = _build_stock_data(
            _record({"dividendYield": 4.5}), benchmark_return_6m=None
        )
        assert data.dividend_yield == pytest.approx(0.045)

    def test_missing_yield(self):
        data = _build_stock_data(_record({}), benchmark_return_6m=None)
        assert data.dividend_yield is None
