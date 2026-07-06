"""Backtest Service — 策略回測引擎，逐日模擬、績效計算."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import StrEnum

import yfinance as yf

from services.stock_service import normalize_ticker

logger = logging.getLogger(__name__)


# ── Enums & Data Classes ─────────────────────────────────────────────────────


class StrategyName(StrEnum):
    MA_CROSS = "ma_cross"
    RSI = "rsi"
    MACD = "macd"
    CUSTOM = "custom"


class TradeAction(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Trade:
    """單筆交易紀錄."""

    date: str
    action: TradeAction
    price: float
    shares: int
    value: float
    reason: str = ""
    fee: float = 0.0  # 本筆交易成本（買=手續費；賣=手續費+證交稅）


@dataclass
class EquityPoint:
    """權益曲線上的一個點."""

    date: str
    equity: float
    drawdown: float = 0.0


@dataclass
class BacktestResult:
    """回測結果."""

    ticker: str
    strategy: str
    period: str
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000
    final_equity: float = 0.0
    total_return: float = 0.0  # %
    annualized_return: float = 0.0  # %
    max_drawdown: float = 0.0  # %
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0  # %
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0  # %
    avg_loss: float = 0.0  # %
    total_fees: float = 0.0  # total transaction costs
    benchmark_return: float = 0.0  # % (buy & hold)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # 模型假設與警語（一律顯示給使用者）
    error: str = ""


# 年化無風險利率（台灣一年期定存約 1.5%），用於夏普比率
RISK_FREE_RATE = 0.015
# 單邊滑價假設（10 bps）：開盤價成交的買賣價差與衝擊成本近似
DEFAULT_SLIPPAGE_RATE = 0.001
# 台股券商單筆最低手續費
TW_MIN_COMMISSION = 20.0


# ── Strategy Implementations ─────────────────────────────────────────────────


def _strategy_ma_cross(
    df,
    short_window: int = 5,
    long_window: int = 20,
) -> list[tuple[str, TradeAction, str]]:
    """均線交叉策略：短均線上穿長均線 → 買入，下穿 → 賣出.

    Returns:
        List of (date_str, action, reason) tuples.
    """
    close = df["Close"]
    ma_short = close.rolling(short_window).mean()
    ma_long = close.rolling(long_window).mean()

    signals: list[tuple[str, TradeAction, str]] = []

    for i in range(long_window, len(df)):
        prev_short = ma_short.iloc[i - 1]
        prev_long = ma_long.iloc[i - 1]
        curr_short = ma_short.iloc[i]
        curr_long = ma_long.iloc[i]

        date_str = df.index[i].strftime("%Y-%m-%d")

        # 金叉：短均線從下方穿越長均線
        if prev_short <= prev_long and curr_short > curr_long:
            signals.append(
                (date_str, TradeAction.BUY, f"MA{short_window} 上穿 MA{long_window}（金叉）")
            )
        # 死叉：短均線從上方穿越長均線
        elif prev_short >= prev_long and curr_short < curr_long:
            signals.append(
                (date_str, TradeAction.SELL, f"MA{short_window} 下穿 MA{long_window}（死叉）")
            )

    return signals


def _strategy_rsi(
    df,
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> list[tuple[str, TradeAction, str]]:
    """RSI 策略：RSI < oversold → 買入；RSI > overbought → 賣出.

    Returns:
        List of (date_str, action, reason) tuples.
    """
    close = df["Close"]
    delta = close.diff()
    # Wilder's smoothing（與券商看盤軟體一致），非簡單移動平均
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    signals: list[tuple[str, TradeAction, str]] = []
    prev_rsi = None

    for i in range(period + 1, len(df)):
        curr_rsi = rsi.iloc[i]
        date_str = df.index[i].strftime("%Y-%m-%d")

        if prev_rsi is not None:
            # RSI 從超賣區回升
            if prev_rsi <= oversold and curr_rsi > oversold:
                signals.append((date_str, TradeAction.BUY, f"RSI 從超賣區回升（{curr_rsi:.1f}）"))
            # RSI 從超買區回落
            elif prev_rsi >= overbought and curr_rsi < overbought:
                signals.append((date_str, TradeAction.SELL, f"RSI 從超買區回落（{curr_rsi:.1f}）"))

        prev_rsi = curr_rsi

    return signals


def _strategy_macd(
    df,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> list[tuple[str, TradeAction, str]]:
    """MACD 策略：MACD 柱狀體由負轉正 → 買入，由正轉負 → 賣出.

    Returns:
        List of (date_str, action, reason) tuples.
    """
    close = df["Close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    signals: list[tuple[str, TradeAction, str]] = []

    for i in range(slow + signal_period, len(df)):
        prev_hist = histogram.iloc[i - 1]
        curr_hist = histogram.iloc[i]
        date_str = df.index[i].strftime("%Y-%m-%d")

        # 金叉：柱狀從負轉正
        if prev_hist <= 0 and curr_hist > 0:
            signals.append(
                (date_str, TradeAction.BUY, f"MACD 金叉（柱狀由負轉正 {curr_hist:.4f}）")
            )
        # 死叉：柱狀從正轉負
        elif prev_hist >= 0 and curr_hist < 0:
            signals.append(
                (date_str, TradeAction.SELL, f"MACD 死叉（柱狀由正轉負 {curr_hist:.4f}）")
            )

    return signals


def _strategy_custom(
    df,
    conditions: list[dict] | None = None,
) -> list[tuple[str, TradeAction, str]]:
    """自訂條件策略：組合多個指標條件.

    conditions example:
    [
        {"indicator": "rsi", "op": "<", "value": 30, "action": "buy"},
        {"indicator": "rsi", "op": ">", "value": 70, "action": "sell"},
        {"indicator": "macd_cross", "op": "==", "value": "golden", "action": "buy"},
    ]
    """
    if not conditions:
        return []

    close = df["Close"]

    # Pre-compute indicators
    # RSI（Wilder's smoothing，與券商看盤軟體一致）
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    # MA
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()

    signals: list[tuple[str, TradeAction, str]] = []
    start = 30  # skip warmup

    for i in range(start, len(df)):
        date_str = df.index[i].strftime("%Y-%m-%d")

        for cond in conditions:
            indicator = cond.get("indicator", "")
            op = cond.get("op", "")
            value = cond.get("value")
            action_str = cond.get("action", "buy")

            action = TradeAction.BUY if action_str == "buy" else TradeAction.SELL
            matched = False
            reason = ""

            if indicator == "rsi":
                curr_rsi = rsi.iloc[i]
                if math.isnan(curr_rsi):
                    continue
                if op == "<" and curr_rsi < value:
                    matched = True
                    reason = f"RSI({curr_rsi:.1f}) < {value}"
                elif op == ">" and curr_rsi > value:
                    matched = True
                    reason = f"RSI({curr_rsi:.1f}) > {value}"

            elif indicator == "macd_cross":
                if i < 1:
                    continue
                prev_hist = histogram.iloc[i - 1]
                curr_hist = histogram.iloc[i]
                if value == "golden" and prev_hist <= 0 and curr_hist > 0:
                    matched = True
                    reason = "MACD 金叉"
                elif value == "death" and prev_hist >= 0 and curr_hist < 0:
                    matched = True
                    reason = "MACD 死叉"

            elif indicator == "ma_cross":
                if i < 1:
                    continue
                prev_short = ma5.iloc[i - 1]
                prev_long = ma20.iloc[i - 1]
                curr_short = ma5.iloc[i]
                curr_long = ma20.iloc[i]
                if value == "golden" and prev_short <= prev_long and curr_short > curr_long:
                    matched = True
                    reason = "MA5 上穿 MA20（金叉）"
                elif value == "death" and prev_short >= prev_long and curr_short < curr_long:
                    matched = True
                    reason = "MA5 下穿 MA20（死叉）"

            if matched:
                signals.append((date_str, action, reason))

    return signals


# ── Simulation Engine ────────────────────────────────────────────────────────


def run_backtest(
    ticker: str,
    strategy: str = "ma_cross",
    period: str = "1y",
    initial_capital: float = 1_000_000,
    strategy_params: dict | None = None,
    custom_conditions: list[dict] | None = None,
) -> BacktestResult:
    """Execute a strategy backtest on historical data.

    Args:
        ticker: Stock ticker (supports TW stock names/codes and US tickers).
        strategy: Strategy name — ma_cross, rsi, macd, or custom.
        period: Backtest period — 3mo, 6mo, 1y, 2y.
        initial_capital: Starting capital (default 1,000,000).
        strategy_params: Optional params for built-in strategies.
        custom_conditions: Required when strategy is "custom".

    Returns:
        BacktestResult with performance metrics, trades, and equity curve.
    """
    ticker = normalize_ticker(ticker)
    params = strategy_params or {}

    result = BacktestResult(
        ticker=ticker,
        strategy=strategy,
        period=period,
        initial_capital=initial_capital,
    )

    # ── Download historical data ──
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
    except Exception as e:
        logger.warning("Failed to fetch history for %s: %s", ticker, e)
        result.error = f"無法取得 {ticker} 的歷史數據：{e}"
        return result

    if df.empty or len(df) < 30:
        result.error = f"{ticker} 歷史數據不足（僅 {len(df)} 天），無法進行回測。"
        return result

    result.start_date = df.index[0].strftime("%Y-%m-%d")
    result.end_date = df.index[-1].strftime("%Y-%m-%d")

    # ── Generate strategy signals ──
    if strategy == StrategyName.MA_CROSS:
        signals = _strategy_ma_cross(
            df,
            short_window=params.get("short_window", 5),
            long_window=params.get("long_window", 20),
        )
    elif strategy == StrategyName.RSI:
        signals = _strategy_rsi(
            df,
            period=params.get("rsi_period", 14),
            oversold=params.get("oversold", 30.0),
            overbought=params.get("overbought", 70.0),
        )
    elif strategy == StrategyName.MACD:
        signals = _strategy_macd(
            df,
            fast=params.get("fast", 12),
            slow=params.get("slow", 26),
            signal_period=params.get("signal_period", 9),
        )
    elif strategy == StrategyName.CUSTOM:
        signals = _strategy_custom(df, conditions=custom_conditions)
    else:
        result.error = f"不支援的策略：{strategy}。可選：ma_cross, rsi, macd, custom"
        return result

    # ── Transaction cost parameters ──
    # Taiwan stock market: broker commission 0.1425% (min NT$20), securities tax 0.3% (sell only)
    is_tw = ticker.endswith(".TW") or ticker.endswith(".TWO")
    commission_rate = 0.001425 if is_tw else 0.0  # broker commission (both sides)
    sell_tax_rate = 0.003 if is_tw else 0.0  # securities transaction tax (sell only)
    min_commission = TW_MIN_COMMISSION if is_tw else 0.0
    slippage_rate = DEFAULT_SLIPPAGE_RATE

    def _commission(amount: float) -> float:
        if commission_rate <= 0 or amount <= 0:
            return 0.0
        return round(max(min_commission, amount * commission_rate), 2)

    # ── Simulate trades ──
    # 成交模型：訊號以第 i 根 K 棒收盤計算，實務上收盤後才能知道訊號，
    # 因此一律以「次一交易日開盤價 ± 滑價」成交，避免 look-ahead 高估績效。
    cash = initial_capital
    shares = 0
    trades: list[Trade] = []
    total_fees = 0.0

    dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
    date_pos = {d: i for i, d in enumerate(dates)}
    open_series = df["Open"]
    close_series = df["Close"]

    for signal_date, action, reason in signals:
        pos = date_pos.get(signal_date)
        if pos is None or pos + 1 >= len(df):
            continue  # 最後一根 K 棒的訊號沒有次日可成交
        exec_idx = pos + 1
        exec_date = dates[exec_idx]
        raw_price = float(open_series.iloc[exec_idx])
        if not raw_price or math.isnan(raw_price) or raw_price <= 0:
            raw_price = float(close_series.iloc[exec_idx])
        if raw_price <= 0:
            continue

        if action == TradeAction.BUY and shares == 0:
            price = raw_price * (1 + slippage_rate)
            affordable = (cash - min_commission) / (1 + commission_rate)
            shares = int(affordable // price)
            if shares <= 0:
                continue
            cost = shares * price
            buy_commission = _commission(cost)
            cash -= cost + buy_commission
            total_fees += buy_commission
            trades.append(
                Trade(
                    date=exec_date,
                    action=TradeAction.BUY,
                    price=round(price, 2),
                    shares=shares,
                    value=round(cost, 2),
                    reason=f"{reason}（{signal_date} 訊號，次日開盤成交）",
                    fee=buy_commission,
                )
            )

        elif action == TradeAction.SELL and shares > 0:
            price = raw_price * (1 - slippage_rate)
            gross_proceeds = shares * price
            sell_commission = _commission(gross_proceeds)
            sell_tax = round(gross_proceeds * sell_tax_rate, 2)
            fee = sell_commission + sell_tax
            total_fees += fee
            cash += gross_proceeds - fee
            trades.append(
                Trade(
                    date=exec_date,
                    action=TradeAction.SELL,
                    price=round(price, 2),
                    shares=shares,
                    value=round(gross_proceeds, 2),
                    reason=f"{reason}（{signal_date} 訊號，次日開盤成交）",
                    fee=fee,
                )
            )
            shares = 0

    # ── Build equity curve ──
    # Re-simulate day by day for equity curve
    sim_cash = initial_capital
    sim_shares = 0
    peak_equity = initial_capital
    equity_curve: list[EquityPoint] = []

    # Convert trades to a date→trade lookup for efficient access
    trade_by_date: dict[str, Trade] = {}
    for t in trades:
        trade_by_date[t.date] = t

    for idx in df.index:
        date_str = idx.strftime("%Y-%m-%d")
        price = float(df.loc[idx, "Close"])

        if date_str in trade_by_date:
            t = trade_by_date[date_str]
            if t.action == TradeAction.BUY:
                sim_shares = t.shares
                sim_cash -= t.value + t.fee
            elif t.action == TradeAction.SELL:
                sim_cash += t.value - t.fee
                sim_shares = 0

        equity = sim_cash + sim_shares * price
        peak_equity = max(peak_equity, equity)
        drawdown = ((peak_equity - equity) / peak_equity) * 100 if peak_equity > 0 else 0

        equity_curve.append(
            EquityPoint(
                date=date_str,
                equity=round(equity, 2),
                drawdown=round(drawdown, 2),
            )
        )

    # ── Compute performance metrics ──
    final_price = float(df["Close"].iloc[-1])
    final_equity = cash + shares * final_price
    result.final_equity = round(final_equity, 2)
    result.total_return = round(((final_equity - initial_capital) / initial_capital) * 100, 2)
    result.total_fees = round(total_fees, 2)

    # Annualized return
    days = (df.index[-1] - df.index[0]).days
    if days > 0:
        years = days / 365.25
        if final_equity > 0 and initial_capital > 0:
            result.annualized_return = round(
                ((final_equity / initial_capital) ** (1 / years) - 1) * 100, 2
            )
        if days < 365:
            result.notes.append(
                f"回測期間僅 {days} 天，年化報酬是短期績效的數學外推，"
                "容易被單一波段放大，參考價值低"
            )

    # Max drawdown
    if equity_curve:
        result.max_drawdown = round(max(p.drawdown for p in equity_curve), 2)

    # Win/loss analysis
    winning = 0
    losing = 0
    win_returns: list[float] = []
    loss_returns: list[float] = []

    for i in range(0, len(trades) - 1, 2):
        if i + 1 < len(trades):
            buy_trade = trades[i]
            sell_trade = trades[i + 1]
            if buy_trade.action == TradeAction.BUY and sell_trade.action == TradeAction.SELL:
                ret = ((sell_trade.price - buy_trade.price) / buy_trade.price) * 100
                if ret > 0:
                    winning += 1
                    win_returns.append(ret)
                else:
                    losing += 1
                    loss_returns.append(ret)

    result.total_trades = len(trades)
    result.winning_trades = winning
    result.losing_trades = losing
    result.win_rate = (
        round((winning / (winning + losing)) * 100, 1) if (winning + losing) > 0 else 0
    )
    result.avg_win = round(sum(win_returns) / len(win_returns), 2) if win_returns else 0
    result.avg_loss = round(sum(loss_returns) / len(loss_returns), 2) if loss_returns else 0

    # Sharpe ratio (annualized, using daily returns of equity curve)
    if len(equity_curve) > 1:
        daily_returns = []
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i - 1].equity
            curr_eq = equity_curve[i].equity
            if prev_eq > 0:
                daily_returns.append((curr_eq - prev_eq) / prev_eq)

        if daily_returns:
            avg_return = sum(daily_returns) / len(daily_returns)
            std_return = (
                sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)
            ) ** 0.5
            if std_return > 0:
                daily_rf = RISK_FREE_RATE / 252
                result.sharpe_ratio = round(
                    ((avg_return - daily_rf) / std_return) * (252**0.5), 2
                )

    # Benchmark: buy & hold return
    first_price = float(df["Close"].iloc[0])
    if first_price > 0:
        result.benchmark_return = round(((final_price - first_price) / first_price) * 100, 2)

    result.trades = trades
    result.equity_curve = equity_curve

    # 模型假設揭露（一律附在結果中，供前端與 Agent 呈現）
    result.notes.append(
        f"成交假設：訊號次一交易日開盤價成交，含單邊滑價 {slippage_rate:+.1%} 近似買賣價差與衝擊成本"
    )
    if is_tw:
        result.notes.append(
            "交易成本：手續費 0.1425%（單筆最低 NT$20，未含折讓）＋賣出證交稅 0.3%"
        )
    result.notes.append(
        "歷史股價為還原權值（隱含股息再投入、未計股利稅）；"
        f"夏普比率已扣除年化 {RISK_FREE_RATE:.1%} 無風險利率"
    )
    result.notes.append("回測為單一標的全額進出模型，未含分批與部位控管；過去績效不代表未來")

    return result


# ── Public helper for Agent tool ─────────────────────────────────────────────


def format_backtest_result(result: BacktestResult) -> str:
    """Format BacktestResult as a human-readable string for the Agent."""
    if result.error:
        return f"❌ 回測失敗：{result.error}"

    parts = [
        f"📊 回測結果：{result.strategy} 策略 × {result.ticker}",
        f"📅 期間：{result.start_date} ~ {result.end_date}",
        "",
        "💰 績效摘要：",
        f"  • 初始資金：${result.initial_capital:,.0f}",
        f"  • 最終淨值：${result.final_equity:,.0f}",
        (
            f"  • 總報酬率：{result.total_return:+.2f}%"
            f"（同一標的 Buy & Hold：{result.benchmark_return:+.2f}%）"
        ),
        f"  • 年化報酬：{result.annualized_return:+.2f}%",
        f"  • 最大回撤：-{result.max_drawdown:.2f}%",
        f"  • 夏普比率：{result.sharpe_ratio:.2f}",
        (
            f"  • 勝率：{result.win_rate:.1f}%"
            f"（{result.winning_trades} 勝 / {result.losing_trades} 敗）"
        ),
        f"  • 總交易次數：{result.total_trades} 次",
        f"  • 總交易成本：${result.total_fees:,.0f}（手續費 + 證交稅）",
    ]

    if result.avg_win or result.avg_loss:
        parts.append(f"  • 平均獲利：{result.avg_win:+.2f}% / 平均虧損：{result.avg_loss:+.2f}%")

    # Show recent trades (last 10)
    if result.trades:
        parts.append("")
        parts.append("📋 交易紀錄（最近 10 筆）：")
        for t in result.trades[-10:]:
            emoji = "🟢" if t.action == TradeAction.BUY else "🔴"
            parts.append(
                f"  {emoji} {t.date} {t.action.value.upper()} "
                f"@ ${t.price:,.2f} × {t.shares} 股 = ${t.value:,.0f}（{t.reason}）"
            )

    if result.notes:
        parts.append("")
        parts.append("📎 模型假設與限制：")
        for note in result.notes:
            parts.append(f"  • {note}")

    return "\n".join(parts)
