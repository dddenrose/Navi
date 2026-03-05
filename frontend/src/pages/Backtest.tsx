import { useState, useCallback } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import {
  runBacktest,
  type BacktestResult,
  type BacktestTrade,
} from "@/lib/api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number, decimals = 0) {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function pnlColor(n: number) {
  if (n > 0) return "text-emerald-400";
  if (n < 0) return "text-red-400";
  return "text-slate-400";
}

const STRATEGIES = [
  {
    name: "ma_cross",
    label: "均線交叉",
    emoji: "📈",
    description: "MA5 上穿 MA20 買入，下穿賣出",
  },
  {
    name: "rsi",
    label: "RSI 指標",
    emoji: "📊",
    description: "RSI < 30 買入，RSI > 70 賣出",
  },
  {
    name: "macd",
    label: "MACD 指標",
    emoji: "📉",
    description: "MACD 金叉買入，死叉賣出",
  },
];

const PERIODS = [
  { value: "3mo", label: "3 個月" },
  { value: "6mo", label: "6 個月" },
  { value: "1y", label: "1 年" },
  { value: "2y", label: "2 年" },
];

// ── Metric Card ──────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  valueColor = "text-slate-200",
  suffix = "",
}: {
  label: string;
  value: string;
  valueColor?: string;
  suffix?: string;
}) {
  return (
    <div
      className="rounded-2xl p-4 md:p-5"
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--border)",
      }}
    >
      <p className="text-xs text-slate-500 mb-1.5">{label}</p>
      <p
        className={`text-sm md:text-base font-semibold tabular-nums ${valueColor}`}
      >
        {value}
        {suffix && (
          <span className="text-xs text-slate-500 ml-1">{suffix}</span>
        )}
      </p>
    </div>
  );
}

// ── Trade Row ────────────────────────────────────────────────────────────────

function TradeRow({ trade, idx }: { trade: BacktestTrade; idx: number }) {
  const isBuy = trade.action === "buy";
  return (
    <tr
      className="border-b transition-colors"
      style={{
        borderColor: "var(--border)",
        background: idx % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
      }}
    >
      <td className="py-3 px-3 text-xs text-slate-400 tabular-nums">
        {trade.date}
      </td>
      <td className="py-3 px-3">
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
            isBuy
              ? "text-emerald-400 bg-emerald-400/10"
              : "text-red-400 bg-red-400/10"
          }`}
        >
          {isBuy ? "買入" : "賣出"}
        </span>
      </td>
      <td className="py-3 px-3 text-xs text-slate-300 tabular-nums text-right">
        ${fmt(trade.price, 2)}
      </td>
      <td className="py-3 px-3 text-xs text-slate-300 tabular-nums text-right">
        {fmt(trade.shares)}
      </td>
      <td className="py-3 px-3 text-xs text-slate-300 tabular-nums text-right">
        ${fmt(trade.value)}
      </td>
      <td className="py-3 px-3 text-xs text-slate-500 max-w-[200px] truncate">
        {trade.reason}
      </td>
    </tr>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function Backtest() {
  const [ticker, setTicker] = useState("");
  const [strategy, setStrategy] = useState("ma_cross");
  const [period, setPeriod] = useState("1y");
  const [capital, setCapital] = useState("1000000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);

  const handleRun = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!ticker.trim()) return;
      setLoading(true);
      setError("");
      setResult(null);
      try {
        const data = await runBacktest({
          ticker: ticker.trim(),
          strategy,
          period,
          initial_capital: parseFloat(capital) || 1_000_000,
        });
        if (data.error) {
          setError(data.error);
        } else {
          setResult(data);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "回測失敗");
      } finally {
        setLoading(false);
      }
    },
    [ticker, strategy, period, capital],
  );

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl md:text-2xl font-semibold text-slate-100">
          📊 策略回測
        </h1>
        <p className="text-sm text-slate-500 mt-2">
          使用歷史數據模擬投資策略績效
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleRun} className="mb-8">
        <div
          className="rounded-2xl p-5 md:p-6 space-y-5"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
          }}
        >
          {/* Ticker input */}
          <div>
            <label className="block text-xs text-slate-500 mb-1.5">
              股票代碼
            </label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="例如 2330、台積電、AAPL"
              required
              className="w-full max-w-sm rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border)",
              }}
            />
          </div>

          {/* Strategy selector */}
          <div>
            <label className="block text-xs text-slate-500 mb-2">策略</label>
            <div className="flex flex-wrap gap-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s.name}
                  type="button"
                  onClick={() => setStrategy(s.name)}
                  className={`
                    rounded-xl px-4 py-2.5 text-sm transition-all duration-200
                    ${
                      strategy === s.name
                        ? "text-white ring-2 ring-indigo-500/60"
                        : "text-slate-400 hover:text-slate-300"
                    }
                  `}
                  style={{
                    background:
                      strategy === s.name
                        ? "rgba(99,102,241,0.15)"
                        : "rgba(255,255,255,0.03)",
                    border: `1px solid ${
                      strategy === s.name
                        ? "rgba(99,102,241,0.4)"
                        : "var(--border)"
                    }`,
                  }}
                >
                  <span className="mr-1.5">{s.emoji}</span>
                  {s.label}
                  {strategy === s.name && (
                    <span className="block text-[11px] text-slate-400 mt-0.5">
                      {s.description}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Period & Capital */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1.5">
                回測期間
              </label>
              <div className="flex gap-2">
                {PERIODS.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setPeriod(p.value)}
                    className={`
                      rounded-lg px-3 py-1.5 text-xs transition-all duration-200
                      ${
                        period === p.value
                          ? "text-white bg-indigo-500/20 ring-1 ring-indigo-500/40"
                          : "text-slate-400 hover:text-slate-300"
                      }
                    `}
                    style={{
                      border: `1px solid ${
                        period === p.value
                          ? "rgba(99,102,241,0.3)"
                          : "var(--border)"
                      }`,
                    }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1.5">
                初始資金（$）
              </label>
              <input
                type="number"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                min="10000"
                step="100000"
                className="w-full max-w-[200px] rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40 tabular-nums"
                style={{
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid var(--border)",
                }}
              />
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !ticker.trim()}
            className="rounded-xl px-6 py-2.5 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
            style={{
              background: "linear-gradient(135deg, var(--primary), #8b5cf6)",
              boxShadow: "0 4px 16px rgba(99,102,241,0.3)",
            }}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeDasharray="60"
                    strokeDashoffset="20"
                    strokeLinecap="round"
                  />
                </svg>
                回測中…
              </span>
            ) : (
              "🚀 執行回測"
            )}
          </button>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div
          className="rounded-2xl p-4 mb-6 text-sm text-red-400"
          style={{
            background: "rgba(248,113,113,0.08)",
            border: "1px solid rgba(248,113,113,0.2)",
          }}
        >
          ❌ {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6 animate-fade-up">
          {/* Summary header */}
          <div
            className="rounded-2xl p-5 md:p-6"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-1">
              <h2 className="text-lg font-semibold text-white">
                {result.ticker}
              </h2>
              <span className="text-sm text-slate-400">
                {STRATEGIES.find((s) => s.name === result.strategy)?.label ??
                  result.strategy}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {result.start_date} ~ {result.end_date}
            </p>
          </div>

          {/* Metric cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="總報酬率"
              value={`${result.total_return >= 0 ? "+" : ""}${fmt(result.total_return, 2)}%`}
              valueColor={pnlColor(result.total_return)}
            />
            <MetricCard
              label="年化報酬"
              value={`${result.annualized_return >= 0 ? "+" : ""}${fmt(result.annualized_return, 2)}%`}
              valueColor={pnlColor(result.annualized_return)}
            />
            <MetricCard
              label="最大回撤"
              value={`-${fmt(result.max_drawdown, 2)}%`}
              valueColor="text-red-400"
            />
            <MetricCard
              label="夏普比率"
              value={fmt(result.sharpe_ratio, 2)}
              valueColor={
                result.sharpe_ratio > 1 ? "text-emerald-400" : "text-slate-300"
              }
            />
            <MetricCard
              label="勝率"
              value={`${fmt(result.win_rate, 1)}%`}
              valueColor={
                result.win_rate >= 50 ? "text-emerald-400" : "text-amber-400"
              }
            />
            <MetricCard label="交易次數" value={`${result.total_trades}`} />
            <MetricCard
              label="最終淨值"
              value={`$${fmt(result.final_equity)}`}
              valueColor={pnlColor(
                result.final_equity - result.initial_capital,
              )}
            />
            <MetricCard
              label="Buy & Hold"
              value={`${result.benchmark_return >= 0 ? "+" : ""}${fmt(result.benchmark_return, 2)}%`}
              valueColor={pnlColor(result.benchmark_return)}
            />
          </div>

          {/* Equity curve chart */}
          {result.equity_curve.length > 0 && (
            <div
              className="rounded-2xl p-5 md:p-6"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
            >
              <h3 className="text-sm font-semibold text-slate-300 mb-4">
                📈 權益曲線
              </h3>
              <div className="h-[280px] md:h-[340px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={result.equity_curve}>
                    <defs>
                      <linearGradient
                        id="equityGrad"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="5%"
                          stopColor={
                            result.total_return >= 0 ? "#4ade80" : "#f87171"
                          }
                          stopOpacity={0.3}
                        />
                        <stop
                          offset="95%"
                          stopColor={
                            result.total_return >= 0 ? "#4ade80" : "#f87171"
                          }
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      tickLine={false}
                      axisLine={false}
                      domain={["auto", "auto"]}
                      tickFormatter={(v: number) =>
                        v >= 1_000_000
                          ? `${(v / 1_000_000).toFixed(1)}M`
                          : `${(v / 1000).toFixed(0)}K`
                      }
                    />
                    <Tooltip
                      contentStyle={{
                        background: "rgba(13,20,36,0.95)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: "12px",
                        backdropFilter: "blur(12px)",
                      }}
                      labelStyle={{ color: "#64748b", fontSize: "11px" }}
                      formatter={(value: number | undefined) => [
                        `$${fmt(value ?? 0)}`,
                        "淨值",
                      ]}
                    />
                    <ReferenceLine
                      y={result.initial_capital}
                      stroke="#475569"
                      strokeDasharray="4 4"
                      label={{
                        value: "初始資金",
                        position: "left",
                        fill: "#475569",
                        fontSize: 10,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="equity"
                      stroke={result.total_return >= 0 ? "#4ade80" : "#f87171"}
                      strokeWidth={2}
                      fill="url(#equityGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Drawdown chart */}
          {result.equity_curve.length > 0 && (
            <div
              className="rounded-2xl p-5 md:p-6"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
            >
              <h3 className="text-sm font-semibold text-slate-300 mb-4">
                📉 回撤曲線
              </h3>
              <div className="h-[180px] md:h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={result.equity_curve}>
                    <defs>
                      <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop
                          offset="5%"
                          stopColor="#f87171"
                          stopOpacity={0.3}
                        />
                        <stop
                          offset="95%"
                          stopColor="#f87171"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      tickLine={false}
                      axisLine={false}
                      domain={[0, "auto"]}
                      tickFormatter={(v: number) => `-${v}%`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "rgba(13,20,36,0.95)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: "12px",
                        backdropFilter: "blur(12px)",
                      }}
                      labelStyle={{ color: "#64748b", fontSize: "11px" }}
                      formatter={(value: number | undefined) => [
                        `-${fmt(value ?? 0, 2)}%`,
                        "回撤",
                      ]}
                    />
                    <Area
                      type="monotone"
                      dataKey="drawdown"
                      stroke="#f87171"
                      strokeWidth={1.5}
                      fill="url(#ddGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Trades table */}
          {result.trades.length > 0 && (
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
            >
              <div className="px-5 pt-5 pb-3">
                <h3 className="text-sm font-semibold text-slate-300">
                  📋 交易紀錄（共 {result.trades.length} 筆）
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th className="py-2.5 px-3 text-[11px] text-slate-500 font-medium">
                        日期
                      </th>
                      <th className="py-2.5 px-3 text-[11px] text-slate-500 font-medium">
                        動作
                      </th>
                      <th className="py-2.5 px-3 text-[11px] text-slate-500 font-medium text-right">
                        價格
                      </th>
                      <th className="py-2.5 px-3 text-[11px] text-slate-500 font-medium text-right">
                        股數
                      </th>
                      <th className="py-2.5 px-3 text-[11px] text-slate-500 font-medium text-right">
                        金額
                      </th>
                      <th className="py-2.5 px-3 text-[11px] text-slate-500 font-medium">
                        原因
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((trade, idx) => (
                      <TradeRow
                        key={`${trade.date}-${trade.action}`}
                        trade={trade}
                        idx={idx}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-[11px] text-slate-600 text-center pb-4">
            ⚠️
            回測結果基於歷史數據，不代表未來績效。所有分析僅供學習與研究用途，不構成投資建議。
          </p>
        </div>
      )}
    </div>
  );
}
