"""picks_tracker 純計算邏輯測試 — 無網路 / 無 Firestore."""

from datetime import date

import pandas as pd
import pytest

from services.screener.picks_tracker import (
    HORIZONS,
    aggregate_tracking,
    compute_tracking,
)


def _series(start: str, prices: list[float]) -> pd.Series:
    idx = pd.bdate_range(start=start, periods=len(prices))
    return pd.Series(prices, index=idx, dtype=float)


# entry 2026-01-05（週一），基準價 100；之後 70 個交易日線性走升
ENTRY = date(2026, 1, 5)


def _stock(after: list[float]) -> pd.Series:
    return _series("2026-01-05", [100.0, *after])


class TestComputeTracking:
    def test_full_horizons(self):
        # 70 個交易日，每日 +1 → T+5 收 105、T+20 收 120、T+60 收 160
        stock = _stock([100.0 + i for i in range(1, 71)])
        bench = _series("2026-01-05", [1000.0] * 71)  # 大盤持平
        t = compute_tracking(ENTRY, stock, bench)
        assert t is not None
        assert t["entry_close_adj"] == 100.0
        assert t["trading_days_elapsed"] == 70
        assert t["complete"] is True
        assert t["return_t5"] == pytest.approx(0.05)
        assert t["return_t20"] == pytest.approx(0.20)
        assert t["return_t60"] == pytest.approx(0.60)
        # 大盤持平 → 超額 = 絕對報酬
        assert t["excess_t20"] == pytest.approx(0.20)
        assert t["max_return"] == pytest.approx(0.70)
        assert t["return_current"] == pytest.approx(0.70)

    def test_partial_horizons_not_complete(self):
        # 只有 10 個交易日 → 只有 t5 有值，complete=False
        stock = _stock([101.0] * 10)
        bench = _series("2026-01-05", [1000.0] * 11)
        t = compute_tracking(ENTRY, stock, bench)
        assert t is not None
        assert t["complete"] is False
        assert t["return_t5"] == pytest.approx(0.01)
        assert "return_t20" not in t
        assert "return_t60" not in t

    def test_excess_vs_benchmark(self):
        # 個股 +10%、大盤 +4%（到 T+20）→ 超額 +6%
        stock = _stock([110.0] * 25)
        bench = _series("2026-01-05", [1000.0] + [1040.0] * 25)
        t = compute_tracking(ENTRY, stock, bench)
        assert t is not None
        assert t["excess_t20"] == pytest.approx(0.10 - 0.04)

    def test_max_drawdown(self):
        stock = _stock([90.0, 80.0, 95.0, 105.0, 102.0])
        bench = _series("2026-01-05", [1000.0] * 6)
        t = compute_tracking(ENTRY, stock, bench)
        assert t is not None
        assert t["max_drawdown"] == pytest.approx(-0.20)
        assert t["max_return"] == pytest.approx(0.05)

    def test_no_basis_returns_none(self):
        # 序列從 entry 之後才開始（如報告日尚未上市）→ 無法建立基準
        stock = _series("2026-02-02", [100.0] * 10)
        bench = _series("2026-01-05", [1000.0] * 30)
        assert compute_tracking(ENTRY, stock, bench) is None

    def test_no_post_entry_data(self):
        # 報告日當天就是最後一筆 → 無追蹤點但仍回傳基準
        stock = _series("2026-01-05", [100.0])
        bench = _series("2026-01-05", [1000.0])
        t = compute_tracking(ENTRY, stock, bench)
        assert t is not None
        assert t["trading_days_elapsed"] == 0
        assert t["complete"] is False
        assert "return_current" not in t

    def test_entry_uses_last_close_at_or_before(self):
        # entry 落在週六（非交易日）→ 用週五收盤當基準
        stock = _series("2026-01-05", [100.0, 102.0, 104.0, 106.0, 110.0] + [120.0] * 10)
        bench = _series("2026-01-05", [1000.0] * 15)
        t = compute_tracking(date(2026, 1, 10), stock, bench)  # 週六
        assert t is not None
        assert t["entry_close_adj"] == 110.0  # 1/9 週五收盤


class TestAggregateTracking:
    def _pick(self, grade: str, t20: float | None, excess: float | None = None) -> dict:
        tracking: dict = {}
        if t20 is not None:
            tracking["return_t20"] = t20
        if excess is not None:
            tracking["excess_t20"] = excess
        return {"final_grade": grade, "tracking": tracking}

    def test_win_rate_and_avg(self):
        picks = [
            self._pick("Pick", 0.10, 0.05),
            self._pick("Pick", -0.05, -0.08),
            self._pick("Strong Pick", 0.20, 0.15),
            self._pick("Strong Pick", 0.02, -0.01),
        ]
        s = aggregate_tracking(picks)
        h = s["horizons"]["t20"]
        assert h["n"] == 4
        assert h["win_rate"] == pytest.approx(0.75)
        assert h["avg_return"] == pytest.approx((0.10 - 0.05 + 0.20 + 0.02) / 4)
        assert h["avg_excess"] == pytest.approx((0.05 - 0.08 + 0.15 - 0.01) / 4)
        assert h["beat_benchmark_rate"] == pytest.approx(0.5)

    def test_by_grade_breakdown(self):
        picks = [
            self._pick("Pick", 0.10),
            self._pick("Strong Pick", -0.02),
        ]
        s = aggregate_tracking(picks)
        assert s["by_grade"]["Pick"]["t20"]["n"] == 1
        assert s["by_grade"]["Pick"]["t20"]["win_rate"] == 1.0
        assert s["by_grade"]["Strong Pick"]["t20"]["win_rate"] == 0.0

    def test_empty_and_missing_horizons(self):
        s = aggregate_tracking([])
        assert s["pick_events"] == 0
        for key in HORIZONS:
            assert s["horizons"][key]["n"] == 0

        # 有 tracking 但尚無 t60 → t60 n=0，不會 KeyError
        s2 = aggregate_tracking([self._pick("Pick", 0.10)])
        assert s2["pick_events"] == 1
        assert s2["horizons"]["t60"]["n"] == 0
