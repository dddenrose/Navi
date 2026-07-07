"""Momentum Rider 簡化版歷史回測 — 重現 MOMENTUM_BACKTEST_NOTES.md 的回測方法.

規則（Pure Technical Momentum Rider，與 services/screener/rules.py 的口徑對齊）:
  Must（全過）:
    M1  多頭排列        收盤 > SMA60 > SMA120
    M2  相對大盤強勢    120 交易日報酬 - ^TWII 同期 > +5%
    M3  量能配合        5 日均量 / 20 日均量 >= 1.0
  Bonus（至少 1 條）:
    MB3 突破訊號        收盤 >= 近 60 日收盤高 × 0.98
    MB4 RSI 健康        Wilder RSI14 在 50-75
  Disqualifier:
    MD2 量價背離        價接近 60 日高但 RSI 落後近 14 日 RSI 高點 5 以上
  略過 M4/M5/MB1/MB2/MD1/MD3/MD4 — yfinance 只有最新財報與籌碼，
  回溯使用會引入 look-ahead bias。

交易模型:
  - 月底（或季底）收盤跑規則 → 次一交易日開盤等權換倉
  - 單邊交易成本 cost_bps（預設 30bps），買賣各收一次
  - 每產業取 bonus 通過數多、120 日報酬強者前 N 檔（與 factor_scorer 排名邏輯一致）

⚠️ 已知限制（結果解讀前必讀）:
  1. Universe 為 industry_data.json「今日仍存在」的股票回溯歷史 →
     含倖存者偏差，動能策略會因此高估報酬。
  2. 使用 yfinance 還原股價（auto_adjust）計算報酬；PE/財報/籌碼規則全數跳過。
  3. 停牌/下市造成的價格缺漏以「最後可得價格出場」近似處理。

Usage:
  cd backend
  uv run python scripts/backtest_momentum.py                      # 2018 ~ 今天
  uv run python scripts/backtest_momentum.py --rebalance QE --top 5
  uv run python scripts/backtest_momentum.py --start 2022-01-01 --end 2025-12-31
  uv run python scripts/backtest_momentum.py --cost-bps 50
  uv run python scripts/backtest_momentum.py --limit 60           # 縮小 universe 快速驗證
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BENCHMARK = "^TWII"
DEFAULT_CACHE_DIR = Path("/tmp/navi_backtest_cache")
INDUSTRY_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "services" / "screener" / "industry_data.json"
)
# 訊號需要 120 交易日均線 + 120 交易日報酬 → 往前多抓約 400 個日曆日
LOOKBACK_CALENDAR_DAYS = 400
DOWNLOAD_BATCH_SIZE = 100
ANNUAL_RISK_FREE = 0.015  # 與 services/backtest_service.py 的夏普口徑一致


# ── Universe ────────────────────────────────────────────────────────────────


def load_universe(limit: int | None = None) -> dict[str, str]:
    """回傳 ticker → industry，來源與線上 screener 相同的 industry_data.json."""
    raw = json.loads(INDUSTRY_DATA_PATH.read_text(encoding="utf-8"))
    ticker_industry: dict[str, str] = {}
    for industry, rows in raw["industries"].items():
        for row in rows:
            ticker_industry[row["ticker"]] = industry
    if limit:
        # 依 ticker 排序後取前 N，確保 --limit 可重現
        keep = sorted(ticker_industry)[:limit]
        ticker_industry = {t: ticker_industry[t] for t in keep}
    return ticker_industry


# ── Data download（yfinance, 本地 cache）───────────────────────────────────


def _cache_key(tickers: list[str], start: str, end: str) -> str:
    h = hashlib.md5(",".join(sorted(tickers)).encode()).hexdigest()[:10]
    return f"ohlcv_{start}_{end}_{len(tickers)}_{h}.pkl"


def download_history(
    tickers: list[str],
    start: str,
    end: str,
    cache_dir: Path,
    refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    """抓全 universe + benchmark 的日線，回傳 {"open","close","volume"} 寬表.

    寬表 index 為交易日、columns 為 ticker。已 auto_adjust（還原股價）。
    """
    import yfinance as yf

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / _cache_key(tickers, start, end)
    if cache_file.exists() and not refresh:
        print(f"📦 使用快取 {cache_file}")
        return pd.read_pickle(cache_file)

    frames: dict[str, list[pd.DataFrame]] = {"open": [], "close": [], "volume": []}
    all_symbols = [*tickers, BENCHMARK]
    for i in range(0, len(all_symbols), DOWNLOAD_BATCH_SIZE):
        batch = all_symbols[i : i + DOWNLOAD_BATCH_SIZE]
        print(f"⬇️  下載 {i + 1}-{i + len(batch)} / {len(all_symbols)} …")
        df = yf.download(
            batch, start=start, end=end,
            auto_adjust=True, group_by="column",
            threads=True, progress=False,
        )
        if df.empty:
            continue
        if not isinstance(df.columns, pd.MultiIndex):
            # 單一 ticker 時 yfinance 回平面欄位
            df.columns = pd.MultiIndex.from_product([df.columns, batch])
        for key, col in (("open", "Open"), ("close", "Close"), ("volume", "Volume")):
            if col in df.columns.get_level_values(0):
                frames[key].append(df[col])

    data = {
        key: pd.concat(parts, axis=1, sort=True).sort_index() if parts else pd.DataFrame()
        for key, parts in frames.items()
    }
    # 去除重複欄位（跨 batch 不會重複，防禦性處理）
    for key in data:
        data[key] = data[key].loc[:, ~data[key].columns.duplicated()]
        data[key].index = pd.DatetimeIndex(data[key].index).tz_localize(None)

    pd.to_pickle(data, cache_file)
    print(f"💾 快取寫入 {cache_file}")
    return data


# ── Indicators（口徑對齊 services/screener/factor_scorer.py）────────────────


def wilder_rsi(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


@dataclass
class SignalPanels:
    """全期間、全 universe 的規則判定結果（bool/float 寬表）."""

    eligible: pd.DataFrame       # M1 & M2 & M3 & (MB3|MB4) & ~MD2
    bonus_count: pd.DataFrame    # MB3 + MB4 通過數（排名用）
    return_6m: pd.DataFrame      # 120 交易日報酬（排名用）


def compute_signals(
    close: pd.DataFrame, volume: pd.DataFrame, bench_close: pd.Series,
) -> SignalPanels:
    sma60 = close.rolling(60).mean()
    sma120 = close.rolling(120).mean()
    ret_6m = close / close.shift(120) - 1
    bench_6m = bench_close / bench_close.shift(120) - 1

    m1 = (close > sma60) & (sma60 > sma120)
    m2 = ret_6m.sub(bench_6m, axis=0) > 0.05
    vol5 = volume.rolling(5).mean()
    vol20 = volume.rolling(20).mean()
    m3 = (vol5 / vol20) >= 1.0

    high_60d = close.rolling(60).max()
    mb3 = close >= high_60d * 0.98
    rsi = wilder_rsi(close)
    mb4 = (rsi >= 50) & (rsi <= 75)

    rsi_high_14 = rsi.rolling(14).max()
    md2 = mb3 & (rsi < rsi_high_14 - 5)

    eligible = m1 & m2 & m3 & (mb3 | mb4) & ~md2
    bonus_count = mb3.astype(int) + mb4.astype(int)
    return SignalPanels(
        eligible=eligible.fillna(False),
        bonus_count=bonus_count,
        return_6m=ret_6m,
    )


# ── Portfolio simulation ────────────────────────────────────────────────────


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp | None = None
    entry_price: float = 0.0
    exit_price: float = 0.0

    def net_return(self, cost: float) -> float:
        gross = self.exit_price / self.entry_price - 1
        return (1 + gross) * (1 - cost) ** 2 - 1  # 買賣各收一次成本


@dataclass
class BacktestResult:
    equity: pd.Series = field(default_factory=pd.Series)
    bench_equity: pd.Series = field(default_factory=pd.Series)
    monthly_returns: pd.Series = field(default_factory=pd.Series)
    trades: list[Trade] = field(default_factory=list)
    forced_exits: int = 0  # 價格缺漏被迫以最後價出場的檔次


def select_portfolio(
    signals: SignalPanels,
    ticker_industry: dict[str, str],
    signal_date: pd.Timestamp,
    top_per_industry: int,
) -> list[str]:
    """signal_date 收盤跑規則 → 每產業取 bonus 多、6M 報酬強的前 N 檔."""
    elig_row = signals.eligible.loc[signal_date]
    candidates = [t for t in elig_row.index[elig_row] if t in ticker_industry]
    by_industry: dict[str, list[str]] = {}
    for t in candidates:
        by_industry.setdefault(ticker_industry[t], []).append(t)

    bonus_row = signals.bonus_count.loc[signal_date]
    ret_row = signals.return_6m.loc[signal_date]
    selected: list[str] = []
    for group in by_industry.values():
        group.sort(key=lambda t: (-bonus_row.get(t, 0), -(ret_row.get(t) or -1.0)))
        selected.extend(group[:top_per_industry])
    return sorted(selected)


def run_backtest(
    data: dict[str, pd.DataFrame],
    ticker_industry: dict[str, str],
    *,
    start: str,
    end: str,
    rebalance: str = "ME",
    top_per_industry: int = 3,
    cost_bps: float = 30.0,
    exec_mode: str = "next_open",
) -> BacktestResult:
    close = data["close"].drop(columns=[BENCHMARK], errors="ignore")
    open_ = data["open"].drop(columns=[BENCHMARK], errors="ignore")
    volume = data["volume"].drop(columns=[BENCHMARK], errors="ignore")
    bench_close = data["close"][BENCHMARK].dropna()

    signals = compute_signals(close, volume, bench_close)
    cost = cost_bps / 10_000

    trading_days = close.index
    in_range = trading_days[(trading_days >= start) & (trading_days <= end)]
    # 每期最後一個交易日 = 訊號日；次一交易日開盤執行
    signal_dates = (
        pd.Series(in_range, index=in_range).resample(rebalance).last().dropna()
    )
    signal_dates = [d for d in signal_dates if d in trading_days]

    result = BacktestResult()
    equity_points: list[tuple[pd.Timestamp, float]] = []
    equity = 1.0
    holdings: dict[str, float] = {}  # ticker → entry open price
    open_trades: dict[str, Trade] = {}

    def price_at_or_before(ticker: str, date: pd.Timestamp) -> float | None:
        s = close[ticker].loc[:date].dropna()
        return float(s.iloc[-1]) if len(s) else None

    # exec_mode="signal_close"：訊號日收盤直接成交（含 look-ahead，僅供
    # 與舊版不可重現數字對照診斷用，不可作為策略績效宣稱）
    exec_px = close if exec_mode == "signal_close" else open_

    for i, sig_date in enumerate(signal_dates):
        if exec_mode == "signal_close":
            exec_date = sig_date
        else:
            after = trading_days[trading_days > sig_date]
            if len(after) == 0:
                break  # 沒有次日可執行 → 本期訊號放棄
            exec_date = after[0]

        target = select_portfolio(signals, ticker_industry, sig_date, top_per_industry)
        # 執行日成交價缺漏者無法買進
        target = [t for t in target if not math.isnan(exec_px.at[exec_date, t])]

        prev_set = set(holdings)
        target_set = set(target)
        sells = prev_set - target_set
        buys = target_set - prev_set

        # 1. 以執行日成交價結清本期：equity × 平均(出場價/進場價)
        if holdings:
            rels = []
            for t, entry_px in holdings.items():
                exit_px = exec_px.at[exec_date, t]
                if math.isnan(exit_px):
                    exit_px = price_at_or_before(t, exec_date) or entry_px
                    result.forced_exits += 1
                rels.append(exit_px / entry_px)
            equity *= float(np.mean(rels))
            for t in sells:
                tr = open_trades.pop(t)
                exit_px = exec_px.at[exec_date, t]
                if math.isnan(exit_px):
                    exit_px = price_at_or_before(t, exec_date) or tr.entry_price
                tr.exit_date = exec_date
                tr.exit_price = float(exit_px)
                result.trades.append(tr)

        # 2. 換手成本：賣出與買進部位各收單邊成本（等權近似）
        n_prev, n_target = len(prev_set), len(target_set)
        sell_frac = len(sells) / n_prev if n_prev else 0.0
        buy_frac = len(buys) / n_target if n_target else 0.0
        equity *= (1 - cost * sell_frac) * (1 - cost * buy_frac)

        # 3. 建立新持倉
        holdings = {t: float(exec_px.at[exec_date, t]) for t in target}
        for t in buys:
            open_trades[t] = Trade(
                ticker=t, entry_date=exec_date,
                entry_price=float(exec_px.at[exec_date, t]),
            )

        # 4. 持有期間逐日估值（下一個執行日之前，用收盤估值）
        next_sig = signal_dates[i + 1] if i + 1 < len(signal_dates) else in_range[-1]
        hold_days = trading_days[(trading_days >= exec_date) & (trading_days <= next_sig)]
        for d in hold_days:
            if holdings:
                rels = [
                    (close.at[d, t] / px)
                    for t, px in holdings.items()
                    if not math.isnan(close.at[d, t])
                ]
                mark = equity * float(np.mean(rels)) if rels else equity
            else:
                mark = equity
            equity_points.append((d, mark))

    # 期末以最後收盤結清未平倉交易（僅供交易統計）
    last_day = in_range[-1]
    for t, tr in open_trades.items():
        px = price_at_or_before(t, last_day)
        if px:
            tr.exit_date = last_day
            tr.exit_price = px
            result.trades.append(tr)

    eq = pd.Series(dict(equity_points)).sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    result.equity = eq
    bench = bench_close.reindex(eq.index).ffill()
    result.bench_equity = bench / bench.iloc[0]
    result.monthly_returns = eq.resample("ME").last().pct_change().dropna()
    return result


# ── Reporting ───────────────────────────────────────────────────────────────


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def print_report(result: BacktestResult, *, cost_bps: float, args) -> None:
    eq, bench = result.equity, result.bench_equity
    if eq.empty:
        print("❌ 沒有任何回測資料點（期間內無合格標的或資料不足）")
        return

    years = (eq.index[-1] - eq.index[0]).days / 365.25
    total_ret = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0
    bench_total = bench.iloc[-1] / bench.iloc[0] - 1
    bench_cagr = (bench.iloc[-1] / bench.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0

    m = result.monthly_returns
    sharpe = float("nan")
    if len(m) > 1 and m.std() > 0:
        sharpe = (m.mean() - ANNUAL_RISK_FREE / 12) / m.std() * math.sqrt(12)

    cost = cost_bps / 10_000
    closed = [t for t in result.trades if t.exit_date is not None and t.entry_price > 0]
    rets = [t.net_return(cost) for t in closed]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    win_rate = len(wins) / len(rets) if rets else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss else float("nan")
    monthly_win = float((m > 0).mean()) if len(m) else 0.0

    print()
    print("=" * 64)
    print("📊 Momentum Rider 簡化版回測結果")
    print("=" * 64)
    print(f"期間          {eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}（{years:.2f} 年）")
    print(
        f"Rebalance     {args.rebalance}  |  每產業 Top {args.top}"
        f"  |  成本 {cost_bps:.0f}bps 單邊  |  exec={args.exec_mode}"
    )
    print("-" * 64)
    print(f"{'指標':<14}{'策略':>12}{'^TWII':>12}{'超額':>12}")
    total_excess = total_ret - bench_total
    print(f"{'總報酬':<14}{total_ret:>+11.2%}{bench_total:>+11.2%}{total_excess:>+11.2%}")
    print(f"{'年化 CAGR':<14}{cagr:>+11.2%}{bench_cagr:>+11.2%}{cagr - bench_cagr:>+11.2%}")
    print(f"{'最大回撤':<14}{max_drawdown(eq):>+11.2%}{max_drawdown(bench):>+11.2%}")
    print(f"{'Sharpe(月)':<14}{sharpe:>11.2f}   （扣年化 {ANNUAL_RISK_FREE:.1%} 無風險利率）")
    print("-" * 64)
    print(f"月勝率        {monthly_win:.1%}（{len(m)} 個月）")
    print(f"交易筆數      {len(closed)}（強制出場 {result.forced_exits} 檔次）")
    print(f"單筆勝率      {win_rate:.1%}")
    print(f"平均賺 / 賠   {avg_win:+.2%} / {avg_loss:+.2%}   賺賠比 {payoff:.2f}")

    # 逐年
    yearly = eq.resample("YE").last().pct_change()
    first_year = eq.resample("YE").last()
    if len(first_year) > 0:
        yearly.iloc[0] = first_year.iloc[0] / eq.iloc[0] - 1
    bench_yearly = bench.resample("YE").last().pct_change()
    bench_first = bench.resample("YE").last()
    if len(bench_first) > 0:
        bench_yearly.iloc[0] = bench_first.iloc[0] / bench.iloc[0] - 1
    print("-" * 64)
    print(f"{'年度':<8}{'策略':>12}{'^TWII':>12}{'超額':>12}")
    for ts, r in yearly.items():
        b = bench_yearly.get(ts, float("nan"))
        print(f"{ts.year:<8}{r:>+11.2%}{b:>+11.2%}{r - b:>+11.2%}")
    print("=" * 64)
    print(
        "⚠️  Universe 為今日仍存在的股票回溯（含倖存者偏差，會高估報酬）；\n"
        "    財報/籌碼規則已跳過；結果僅供研究，不構成投資建議。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Momentum Rider 簡化版歷史回測")
    parser.add_argument("--start", default="2018-02-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--rebalance", choices=["ME", "QE"], default="ME",
                        help="ME=月底 / QE=季底")
    parser.add_argument("--top", type=int, default=3, help="每產業取前 N 檔")
    parser.add_argument("--cost-bps", type=float, default=30.0, help="單邊交易成本（bps）")
    parser.add_argument(
        "--exec", dest="exec_mode", choices=["next_open", "signal_close"],
        default="next_open",
        help="成交時點：next_open=次日開盤（預設，無 look-ahead）；"
             "signal_close=訊號日收盤（含 look-ahead，僅供與舊數字對照診斷）",
    )
    parser.add_argument("--limit", type=int, default=None, help="只取前 N 檔 universe（快速驗證）")
    parser.add_argument("--tickers", default=None, help="逗號分隔，覆寫 universe（快速驗證）")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--refresh", action="store_true", help="忽略快取重新下載")
    args = parser.parse_args()

    ticker_industry = load_universe(limit=args.limit)
    if args.tickers:
        keep = [t.strip() for t in args.tickers.split(",") if t.strip()]
        ticker_industry = {t: ticker_industry.get(t, "未分類") for t in keep}
    tickers = sorted(ticker_industry)
    print(f"🌐 Universe: {len(tickers)} 檔（{len(set(ticker_industry.values()))} 產業）")

    cache_dir = Path(args.cache_dir)
    dl_start = (
        pd.Timestamp(args.start) - pd.Timedelta(days=LOOKBACK_CALENDAR_DAYS)
    ).strftime("%Y-%m-%d")
    data = download_history(tickers, dl_start, args.end, cache_dir, refresh=args.refresh)
    if data["close"].empty or BENCHMARK not in data["close"]:
        print("❌ 價格資料下載失敗（含 ^TWII），請稍後重試或加 --refresh")
        sys.exit(1)

    result = run_backtest(
        data, ticker_industry,
        start=args.start, end=args.end,
        rebalance=args.rebalance,
        top_per_industry=args.top,
        cost_bps=args.cost_bps,
        exec_mode=args.exec_mode,
    )
    print_report(result, cost_bps=args.cost_bps, args=args)

    out = cache_dir / "equity_curve.csv"
    pd.DataFrame({
        "equity": result.equity,
        "benchmark": result.bench_equity,
    }).to_csv(out, index_label="date")
    print(f"\n📈 Equity curve → {out}")


if __name__ == "__main__":
    main()
