"""回測引擎測試 — 成交模型（次日開盤）、交易成本、績效計算.

用合成 OHLC 資料 mock yfinance，驗證：
1. 訊號不會在同一根 K 棒收盤成交（look-ahead 防護）
2. 成交價 = 次日開盤 ± 滑價
3. 台股手續費有單筆最低 NT$20
4. 短期間回測附年化外推警語
5. 模型假設 notes 一律回傳
"""

from unittest.mock import MagicMock, patch

import pandas as pd

from services.backtest_service import (
    DEFAULT_SLIPPAGE_RATE,
    TW_MIN_COMMISSION,
    TradeAction,
    run_backtest,
)


def _make_df(closes: list[float], start: str = "2025-01-01") -> pd.DataFrame:
    """合成日線：Open 設為前日收盤（模擬跳空前的自然開盤）。"""
    idx = pd.bdate_range(start=start, periods=len(closes))
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame(
        {
            "Open": opens,
            "High": [max(o, c) * 1.01 for o, c in zip(opens, closes)],
            "Low": [min(o, c) * 0.99 for o, c in zip(opens, closes)],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


def _run_with_prices(closes: list[float], ticker: str = "2330.TW", **kwargs):
    df = _make_df(closes)
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    with (
        patch("services.backtest_service.yf.Ticker", return_value=mock_ticker),
        patch("services.backtest_service.normalize_ticker", return_value=ticker),
    ):
        return run_backtest(ticker, **kwargs), df


# 先跌後漲再跌：MA5/MA20 會產生一次金叉與一次死叉
GOLDEN_DEATH_PATH = (
    [100 - i for i in range(25)]  # 100 → 76 下跌（建立空頭均線）
    + [76 + 3 * i for i in range(15)]  # 急漲 → 金叉
    + [118 - 4 * i for i in range(15)]  # 急跌 → 死叉
)


class TestExecutionModel:
    def test_trades_execute_next_day_not_signal_day(self):
        result, df = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        assert not result.error
        assert result.total_trades >= 2

        dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
        for t in result.trades:
            # reason 內嵌訊號日：「…（YYYY-MM-DD 訊號，次日開盤成交）」
            signal_date = t.reason.split("（")[-1].split(" ")[0]
            assert dates.index(t.date) == dates.index(signal_date) + 1, (
                f"交易 {t.date} 應在訊號日 {signal_date} 的次一交易日成交"
            )

    def test_buy_price_is_next_open_plus_slippage(self):
        result, df = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        buys = [t for t in result.trades if t.action == TradeAction.BUY]
        assert buys
        dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
        for t in buys:
            exec_open = float(df["Open"].iloc[dates.index(t.date)])
            assert t.price == round(exec_open * (1 + DEFAULT_SLIPPAGE_RATE), 2)

    def test_sell_price_is_next_open_minus_slippage(self):
        result, df = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        sells = [t for t in result.trades if t.action == TradeAction.SELL]
        assert sells
        dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
        for t in sells:
            exec_open = float(df["Open"].iloc[dates.index(t.date)])
            assert t.price == round(exec_open * (1 - DEFAULT_SLIPPAGE_RATE), 2)


class TestTransactionCosts:
    def test_tw_minimum_commission(self):
        # 小資金：手續費按比例會低於 20 元，應收最低 20
        result, _ = _run_with_prices(
            GOLDEN_DEATH_PATH, strategy="ma_cross", initial_capital=10_000
        )
        buys = [t for t in result.trades if t.action == TradeAction.BUY]
        assert buys
        for t in buys:
            assert t.fee >= TW_MIN_COMMISSION

    def test_us_ticker_has_no_commission(self):
        result, _ = _run_with_prices(
            GOLDEN_DEATH_PATH, ticker="AAPL", strategy="ma_cross"
        )
        assert result.total_fees == 0.0

    def test_sell_fee_includes_tax(self):
        result, _ = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        sells = [t for t in result.trades if t.action == TradeAction.SELL]
        assert sells
        for t in sells:
            # 賣出成本 = 手續費(≥0.1425%) + 證交稅 0.3% > 0.4% 的成交額
            assert t.fee >= t.value * 0.004


class TestMetricsIntegrity:
    def test_equity_curve_ends_at_final_equity(self):
        result, _ = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        assert result.equity_curve
        assert abs(result.equity_curve[-1].equity - result.final_equity) < 1.0

    def test_short_period_has_annualization_warning(self):
        result, _ = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        assert any("年化" in n and "外推" in n for n in result.notes)

    def test_notes_disclose_assumptions(self):
        result, _ = _run_with_prices(GOLDEN_DEATH_PATH, strategy="ma_cross")
        joined = "\n".join(result.notes)
        assert "次一交易日開盤" in joined
        assert "還原權值" in joined
        assert "無風險利率" in joined

    def test_insufficient_data_returns_error(self):
        result, _ = _run_with_prices([100.0] * 10, strategy="ma_cross")
        assert result.error
