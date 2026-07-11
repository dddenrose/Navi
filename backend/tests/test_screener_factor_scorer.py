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


class TestDividendYieldSanity:
    def test_absurd_yield_treated_as_missing(self):
        # 若 yfinance 語意漂移（改回小數形式 0.30 = 30%… 或資料異常），
        # 除以 100 後 > 15% 的殖利率視為可疑 → 當缺值，寧缺勿錯
        d = _build_stock_data(
            _record({"dividendYield": 2000.0}), benchmark_return_6m=None
        )
        assert d.dividend_yield is None


class TestPeRawForDisqualifiers:
    def test_extreme_pe_kept_in_pe_raw(self):
        # PE 300：估值欄位消毒為 None，但 pe_raw 保留給 MD1/VD4 剔除判斷
        d = _build_stock_data(
            _record({"trailingPE": 300.0}), benchmark_return_6m=None
        )
        assert d.pe is None
        assert d.pe_raw == 300.0

    def test_no_forward_pe_fallback(self):
        # 只用 trailingPE —— forwardPE 口徑不同，不得混入產業統計
        d = _build_stock_data(
            _record({"forwardPE": 18.0}), benchmark_return_6m=None
        )
        assert d.pe is None
        assert d.pe_raw is None


class TestSelectTopPicks:
    def _evaluated(self, ticker, industry, *, bonus, strength, qualified=True):
        from services.screener.factor_scorer import EvaluatedStock
        from services.screener.rules import ScoringTrace, StockData

        data = StockData(
            ticker=ticker, name=ticker, industry=industry, price=100.0,
            rel_strength_6m=strength,
        )
        trace = ScoringTrace(profile="momentum")
        trace.verdict = "qualified" if qualified else "rejected"
        trace.bonus_passed = bonus
        return EvaluatedStock(data=data, trace=trace)

    def test_global_ranking_with_industry_cap(self):
        from services.screener.factor_scorer import select_top_picks

        results = [
            self._evaluated("A.TW", "半導體", bonus=3, strength=0.5),
            self._evaluated("B.TW", "半導體", bonus=3, strength=0.4),
            self._evaluated("C.TW", "半導體", bonus=3, strength=0.3),  # 超過產業上限
            self._evaluated("D.TW", "航運", bonus=2, strength=0.9),
            self._evaluated("E.TW", "金融", bonus=0, strength=0.1, qualified=False),
        ]
        picks = select_top_picks(results, "momentum", total=3, max_per_industry=2)
        tickers = [p.data.ticker for p in picks]
        assert tickers == ["A.TW", "B.TW", "D.TW"]  # C 被產業上限擋下、E 未資格化
        assert [p.rank_overall for p in picks] == [1, 2, 3]

    def test_total_cap(self):
        from services.screener.factor_scorer import select_top_picks

        results = [
            self._evaluated(f"T{i}.TW", f"產業{i}", bonus=1, strength=0.1 * i)
            for i in range(8)
        ]
        picks = select_top_picks(results, "momentum", total=5, max_per_industry=2)
        assert len(picks) == 5
        # 依 strength 降冪
        strengths = [p.data.rel_strength_6m for p in picks]
        assert strengths == sorted(strengths, reverse=True)
