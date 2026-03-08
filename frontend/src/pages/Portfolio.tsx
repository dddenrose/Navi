import { useState, useEffect, useCallback } from "react";
import {
  getPortfolio,
  addHolding,
  deleteHolding,
  type PortfolioSummary,
  type HoldingWithPrice,
} from "@/lib/api";
import { fmt, pnlColor, pnlBg } from "@/lib/format";

// ── Add Holding Modal ────────────────────────────────────────────────────────

function AddHoldingModal({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (data: {
    ticker: string;
    shares: number;
    avg_cost: number;
    name: string;
    notes: string;
  }) => Promise<void>;
}) {
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [avgCost, setAvgCost] = useState("");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker || !shares || !avgCost) return;
    setLoading(true);
    setError("");
    try {
      await onAdd({
        ticker: ticker.toUpperCase(),
        shares: parseFloat(shares),
        avg_cost: parseFloat(avgCost),
        name,
        notes,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "新增失敗");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{
        background: "var(--modal-overlay)",
        backdropFilter: "blur(4px)",
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl p-6 space-y-4"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
        }}
      >
        <h2 className="text-lg font-semibold text-white">新增持股</h2>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              股票代碼 *
            </label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="例如 2330.TW"
              required
              className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
              style={{
                background: "var(--overlay-bg)",
                border: "1px solid var(--border)",
              }}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-500 mb-1">
                股數 *
              </label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="1000"
                required
                min="0"
                step="any"
                className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
                style={{
                  background: "var(--overlay-bg)",
                  border: "1px solid var(--border)",
                }}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">
                平均成本 *
              </label>
              <input
                type="number"
                value={avgCost}
                onChange={(e) => setAvgCost(e.target.value)}
                placeholder="580"
                required
                min="0"
                step="any"
                className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
                style={{
                  background: "var(--overlay-bg)",
                  border: "1px solid var(--border)",
                }}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              股票名稱
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="台積電"
              className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
              style={{
                background: "var(--overlay-bg)",
                border: "1px solid var(--border)",
              }}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">備註</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="長期投資"
              className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
              style={{
                background: "var(--overlay-bg)",
                border: "1px solid var(--border)",
              }}
            />
          </div>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-xl px-4 py-2.5 text-sm text-slate-400 hover:text-white transition-colors"
            style={{
              background: "var(--overlay-bg)",
              border: "1px solid var(--border)",
            }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={loading || !ticker || !shares || !avgCost}
            className="flex-1 rounded-xl px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 transition-opacity"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            }}
          >
            {loading ? "新增中…" : "新增"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Holdings Table Row ───────────────────────────────────────────────────────

function HoldingRow({
  holding,
  totalValue,
  onDelete,
}: {
  holding: HoldingWithPrice;
  totalValue: number;
  onDelete: (id: string) => void;
}) {
  const pct = totalValue > 0 ? (holding.market_value / totalValue) * 100 : 0;

  return (
    <tr className="group" style={{ borderBottom: "1px solid var(--border)" }}>
      <td className="py-4 px-4">
        <div>
          <span className="text-sm font-medium text-white">
            {holding.ticker}
          </span>
          {holding.name && (
            <span className="text-xs text-slate-600 ml-2">{holding.name}</span>
          )}
        </div>
      </td>
      <td className="py-4 px-3 text-right text-sm text-slate-300 tabular-nums">
        {fmt(holding.shares)}
      </td>
      <td className="py-4 px-3 text-right text-sm text-slate-400 tabular-nums">
        ${fmt(holding.avg_cost, 2)}
      </td>
      <td className="py-4 px-3 text-right text-sm text-slate-200 tabular-nums">
        {holding.current_price != null
          ? `$${fmt(holding.current_price, 2)}`
          : "—"}
      </td>
      <td className="py-4 px-3 text-right text-sm text-slate-300 tabular-nums">
        ${fmt(holding.market_value)}
      </td>
      <td
        className={`py-4 px-3 text-right text-sm tabular-nums ${pnlColor(holding.pnl)}`}
      >
        {holding.pnl >= 0 ? "+" : ""}
        {fmt(holding.pnl)}
        <span className="text-xs ml-1 opacity-70">
          ({holding.pnl_percent >= 0 ? "+" : ""}
          {holding.pnl_percent.toFixed(2)}%)
        </span>
      </td>
      <td className="py-4 px-3 text-right text-sm text-slate-500 tabular-nums">
        {pct.toFixed(1)}%
      </td>
      <td className="py-4 px-3 text-right">
        <button
          onClick={() => onDelete(holding.id)}
          className="opacity-0 group-hover:opacity-100 text-xs text-slate-600 hover:text-red-400 transition-opacity"
          aria-label={`刪除 ${holding.ticker}`}
        >
          ✕
        </button>
      </td>
    </tr>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");

  const fetchPortfolio = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getPortfolio();
      setPortfolio(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  const handleAdd = async (data: {
    ticker: string;
    shares: number;
    avg_cost: number;
    name: string;
    notes: string;
  }) => {
    await addHolding(data);
    await fetchPortfolio();
  };

  const handleDelete = async (holdingId: string) => {
    await deleteHolding(holdingId);
    await fetchPortfolio();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <p className="text-sm text-slate-500">載入投資組合中…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  const summary = portfolio;
  const hasHoldings = summary && summary.holdings_count > 0;

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 md:mb-10">
        <div>
          <h1 className="text-2xl font-semibold text-white">💼 投資組合</h1>
          <p className="text-sm text-slate-500 mt-1">即時市值、損益追蹤</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
          style={{
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
          }}
        >
          + 新增持股
        </button>
      </div>

      {/* Summary cards */}
      {hasHoldings && summary && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4 mb-8 md:mb-10">
          <div
            className="rounded-2xl p-5"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500 mb-2">總市值</p>
            <p className="text-lg font-semibold text-white tabular-nums">
              ${fmt(summary.total_value)}
            </p>
          </div>
          <div
            className="rounded-2xl p-5"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500 mb-2">總成本</p>
            <p className="text-lg font-semibold text-slate-300 tabular-nums">
              ${fmt(summary.total_cost)}
            </p>
          </div>
          <div
            className="rounded-2xl p-5"
            style={{
              background: pnlBg(summary.total_pnl),
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500 mb-2">總損益</p>
            <p
              className={`text-lg font-semibold tabular-nums ${pnlColor(summary.total_pnl)}`}
            >
              {summary.total_pnl >= 0 ? "+" : ""}${fmt(summary.total_pnl)}
            </p>
          </div>
          <div
            className="rounded-2xl p-5"
            style={{
              background: pnlBg(summary.total_pnl),
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500 mb-2">報酬率</p>
            <p
              className={`text-lg font-semibold tabular-nums ${pnlColor(summary.total_pnl_percent)}`}
            >
              {summary.total_pnl_percent >= 0 ? "+" : ""}
              {summary.total_pnl_percent.toFixed(2)}%
            </p>
          </div>
        </div>
      )}

      {/* Holdings table */}
      {hasHoldings && summary ? (
        <div
          className="rounded-2xl overflow-hidden"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div
            className="px-6 py-4"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="text-sm font-medium text-slate-300">
              持股明細（{summary.holdings_count} 檔）
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr
                  className="text-xs text-slate-500"
                  style={{ borderBottom: "1px solid var(--border)" }}
                >
                  <th className="text-left py-3 px-4 font-medium">股票</th>
                  <th className="text-right py-3 px-3 font-medium">股數</th>
                  <th className="text-right py-3 px-3 font-medium">成本</th>
                  <th className="text-right py-3 px-3 font-medium">現價</th>
                  <th className="text-right py-3 px-3 font-medium">市值</th>
                  <th className="text-right py-3 px-3 font-medium">損益</th>
                  <th className="text-right py-3 px-3 font-medium">佔比</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {summary.holdings
                  .sort((a, b) => b.market_value - a.market_value)
                  .map((h) => (
                    <HoldingRow
                      key={h.id}
                      holding={h}
                      totalValue={summary.total_value}
                      onDelete={handleDelete}
                    />
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div
          className="rounded-2xl p-16 text-center"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="text-4xl mb-4">💼</div>
          <h2 className="text-lg font-medium text-white mb-2">
            開始建立你的投資組合
          </h2>
          <p className="text-sm text-slate-500 mb-6">
            新增持股後，即可追蹤即時市值與損益
          </p>
          <button
            onClick={() => setShowAdd(true)}
            className="rounded-xl px-6 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            }}
          >
            + 新增第一筆持股
          </button>
        </div>
      )}

      {/* Add holding modal */}
      {showAdd && (
        <AddHoldingModal onClose={() => setShowAdd(false)} onAdd={handleAdd} />
      )}
    </div>
  );
}
