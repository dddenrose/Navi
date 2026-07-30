import { useState, useEffect } from "react";
import { Pencil, X, TriangleAlert, Briefcase } from "lucide-react";
import {
  type HoldingWithPrice,
  type AddTransactionInput,
} from "@/lib/api";
import {
  useAddHolding,
  useAddTransaction,
  useDeleteHolding,
  usePortfolio,
  usePortfolioTransactions,
  useTransactionCostEstimate,
  useUpdateHolding,
} from "@/lib/queries/portfolio";
import { fmt, pnlColor, pnlBg } from "@/lib/format";
import { useCountUp } from "@/lib/useCountUp";
import TickerAutocomplete from "@/components/TickerAutocomplete";
import { usePrivacyStore } from "@/store/privacyStore";

// ── Eye glyph（顯示/隱藏金額切換）─────────────────────────────────────────────

function EyeGlyph({
  off,
  className = "h-4 w-4",
}: {
  /** true = 目前隱藏中（顯示劃線眼睛，提示點擊可顯示） */
  off: boolean;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {off ? (
        // 劃線眼睛：目前隱藏中
        <>
          <path d="M9.88 5.09A9.6 9.6 0 0 1 12 4.85c4.64 0 8.57 3.02 9.96 7.15a11.9 11.9 0 0 1-2.28 3.63M6.16 6.16A11.9 11.9 0 0 0 2.04 12c1.39 4.13 5.32 7.15 9.96 7.15a9.6 9.6 0 0 0 4.2-.96" />
          <path d="M10.58 10.58a2 2 0 0 0 2.83 2.83" />
          <path d="M3 3l18 18" />
        </>
      ) : (
        // 眼睛：目前顯示中
        <>
          <path d="M2.04 12C3.43 7.87 7.36 4.85 12 4.85s8.57 3.02 9.96 7.15c-1.39 4.13-5.32 7.15-9.96 7.15S3.43 16.13 2.04 12z" />
          <circle cx="12" cy="12" r="2.6" />
        </>
      )}
    </svg>
  );
}

// ── 隱私遮罩圓點（鎖定時取代金額，銀行 App 風格；只遮數字、不蓋整區）──────────

/**
 * 鎖定時顯示的一串圓點，取代真實數字。
 * - 保留幣別/百分比符號，維持「這裡有個金額被藏起來」的語意
 * - 色調中性、tabular-nums 對齊、淡入、不可選取
 */
function Masked({
  prefix = "",
  suffix = "",
  count = 6,
}: {
  prefix?: string;
  suffix?: string;
  count?: number;
}) {
  return (
    <span
      className="animate-fade-in select-none tabular-nums text-ink-muted"
      aria-label="金額已隱藏"
      title="已鎖定，點右上角眼睛顯示"
    >
      {prefix}
      <span className="tracking-[0.18em]">{"•".repeat(count)}</span>
      {suffix}
    </span>
  );
}

// ── Transaction Modal（買/賣，含台股費稅即時估算）────────────────────────────

function TransactionModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (data: AddTransactionInput) => Promise<void>;
}) {
  const [action, setAction] = useState<"buy" | "sell">("buy");
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [tradeDate, setTradeDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // 輸入完整時向後端估算費稅（debounce 400ms）。
  // effect 只負責節流出「已定案的輸入」，請求與快取交給 query。
  const [estimateInput, setEstimateInput] = useState<{
    ticker: string;
    shares: number;
    price: number;
  } | null>(null);

  useEffect(() => {
    const s = parseFloat(shares);
    const p = parseFloat(price);
    if (!ticker || !s || !p || s <= 0 || p <= 0) {
      setEstimateInput(null);
      return;
    }
    const t = setTimeout(
      () => setEstimateInput({ ticker: ticker.toUpperCase(), shares: s, price: p }),
      400,
    );
    return () => clearTimeout(t);
  }, [ticker, shares, price]);

  const estimate =
    useTransactionCostEstimate({
      ticker: estimateInput?.ticker ?? "",
      action,
      shares: estimateInput?.shares ?? 0,
      price: estimateInput?.price ?? 0,
      enabled: estimateInput !== null,
    }).data ?? null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker || !shares || !price) return;
    setLoading(true);
    setError("");
    try {
      await onSubmit({
        ticker: ticker.toUpperCase(),
        action,
        shares: parseFloat(shares),
        price: parseFloat(price),
        trade_date: tradeDate || undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "交易記錄失敗");
    } finally {
      setLoading(false);
    }
  };

  const inputCls = "input-field rounded-xl px-4 py-2.5 text-sm";

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
        className="card w-full max-w-md p-6 space-y-4"
      >
        <h2 className="text-lg font-semibold text-ink-strong">記錄交易</h2>

        <div className="flex gap-2">
          {(["buy", "sell"] as const).map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setAction(a)}
              className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                action === a ? "text-ink-strong" : "text-ink-muted"
              }`}
              style={{
                background:
                  action === a
                    ? a === "buy"
                      ? "rgba(248,113,113,0.2)"
                      : "rgba(52,211,153,0.2)"
                    : "var(--surface-1)",
                border: `1px solid ${
                  action === a
                    ? a === "buy"
                      ? "rgba(248,113,113,0.4)"
                      : "rgba(52,211,153,0.4)"
                    : "var(--border-subtle)"
                }`,
              }}
            >
              {a === "buy" ? "買入" : "賣出"}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-ink-muted mb-1">
              股票代碼 *
            </label>
            <TickerAutocomplete
              value={ticker}
              onChange={setTicker}
              onSelect={(s) => setTicker(s.ticker)}
              placeholder="輸入代碼或名稱，例如 2330 / 台積電"
              required
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-ink-muted mb-1">
                股數 *
              </label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="1000（1 張 = 1000 股）"
                required
                min="0"
                step="any"
                className={inputCls}
              />
            </div>
            <div>
              <label className="block text-xs text-ink-muted mb-1">
                成交價 *
              </label>
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="600"
                required
                min="0"
                step="any"
                className={inputCls}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1">交易日</label>
            <input
              type="date"
              value={tradeDate}
              onChange={(e) => setTradeDate(e.target.value)}
              className={inputCls}
            />
          </div>
        </div>

        {estimate && (estimate.fee > 0 || estimate.tax > 0) && (
          <p className="text-xs text-ink-muted">
            預估手續費 ${fmt(estimate.fee, 2)}
            {estimate.tax > 0 && <>、證交稅 ${fmt(estimate.tax, 2)}</>}
            （台股牌告費率，將計入成本／損益）
          </p>
        )}

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost flex-1 justify-center rounded-xl px-4 py-2.5 text-sm"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={loading || !ticker || !shares || !price}
            className="btn btn-primary flex-1 justify-center rounded-xl px-4 py-2.5 text-sm disabled:opacity-40 transition-opacity"
          >
            {loading ? "記錄中…" : action === "buy" ? "記錄買入" : "記錄賣出"}
          </button>
        </div>
      </form>
    </div>
  );
}

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

  const inputCls = "input-field rounded-xl px-4 py-2.5 text-sm";

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
        className="card w-full max-w-md p-6 space-y-4"
      >
        <h2 className="text-lg font-semibold text-ink-strong">新增持股</h2>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-ink-muted mb-1">
              股票代碼 *
            </label>
            <TickerAutocomplete
              value={ticker}
              onChange={setTicker}
              onSelect={(s) => {
                setTicker(s.ticker);
                setName(s.name); // 自動帶出股票名稱
              }}
              placeholder="輸入代碼或名稱，例如 2330 / 台積電"
              required
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-ink-muted mb-1">
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
                className={inputCls}
              />
            </div>
            <div>
              <label className="block text-xs text-ink-muted mb-1">
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
                className={inputCls}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1">
              股票名稱
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="選填，選擇代碼後自動帶入（如：台積電）"
              className={inputCls}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1">備註</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="長期投資"
              className={inputCls}
            />
          </div>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost flex-1 justify-center rounded-xl px-4 py-2.5 text-sm"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={loading || !ticker || !shares || !avgCost}
            className="btn btn-primary flex-1 justify-center rounded-xl px-4 py-2.5 text-sm disabled:opacity-40 transition-opacity"
          >
            {loading ? "新增中…" : "新增"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Edit Holding Modal ───────────────────────────────────────────────────────

function EditHoldingModal({
  holding,
  onClose,
  onSave,
}: {
  holding: HoldingWithPrice;
  onClose: () => void;
  onSave: (
    holdingId: string,
    data: { shares: number; avg_cost: number; notes: string },
  ) => Promise<void>;
}) {
  const [shares, setShares] = useState(String(holding.shares));
  const [avgCost, setAvgCost] = useState(String(holding.avg_cost));
  const [notes, setNotes] = useState(holding.notes ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const s = parseFloat(shares);
    const c = parseFloat(avgCost);
    if (!s || !c || s <= 0 || c <= 0) {
      setError("股數與平均成本需為大於 0 的數字");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await onSave(holding.id, { shares: s, avg_cost: c, notes });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失敗");
    } finally {
      setLoading(false);
    }
  };

  const inputCls = "input-field rounded-xl px-4 py-2.5 text-sm";

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
        className="card w-full max-w-md p-6 space-y-4"
      >
        <div>
          <h2 className="text-lg font-semibold text-ink-strong">編輯持股</h2>
          <p className="text-sm text-ink-muted mt-0.5">
            {holding.ticker}
            {holding.name && <span className="ml-2">{holding.name}</span>}
          </p>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-ink-muted mb-1">
                股數 *
              </label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                required
                min="0"
                step="any"
                className={inputCls}
              />
            </div>
            <div>
              <label className="block text-xs text-ink-muted mb-1">
                平均成本 *
              </label>
              <input
                type="number"
                value={avgCost}
                onChange={(e) => setAvgCost(e.target.value)}
                required
                min="0"
                step="any"
                className={inputCls}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1">備註</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="長期投資"
              className={inputCls}
            />
          </div>
          <p className="text-xs text-ink-faint">
            如需更換股票代碼，請刪除本筆後重新新增。
          </p>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost flex-1 justify-center rounded-xl px-4 py-2.5 text-sm"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary flex-1 justify-center rounded-xl px-4 py-2.5 text-sm disabled:opacity-40 transition-opacity"
          >
            {loading ? "更新中…" : "儲存"}
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
  locked,
  onEdit,
  onDelete,
}: {
  holding: HoldingWithPrice;
  totalValue: number;
  locked: boolean;
  onEdit: (holding: HoldingWithPrice) => void;
  onDelete: (id: string) => void;
}) {
  const pct = totalValue > 0 ? (holding.market_value / totalValue) * 100 : 0;

  return (
    <tr className="group border-b border-line-subtle">
      <td className="py-4 px-4">
        <div>
          <span className="text-sm font-medium text-ink-strong">
            {holding.ticker}
          </span>
          {holding.name && (
            <span className="text-xs text-ink-faint ml-2">{holding.name}</span>
          )}
        </div>
      </td>
      <td className="py-4 px-3 text-right text-sm text-ink tabular-nums">
        {locked ? <Masked count={4} /> : fmt(holding.shares)}
      </td>
      <td className="py-4 px-3 text-right text-sm text-ink-secondary tabular-nums">
        {locked ? (
          <Masked prefix="$" count={5} />
        ) : (
          <>${fmt(holding.avg_cost, 2)}</>
        )}
      </td>
      <td className="py-4 px-3 text-right text-sm text-ink tabular-nums">
        {holding.current_price != null
          ? `$${fmt(holding.current_price, 2)}`
          : "—"}
      </td>
      <td className="py-4 px-3 text-right text-sm text-ink tabular-nums">
        {locked ? <Masked prefix="$" /> : <>${fmt(holding.market_value)}</>}
      </td>
      <td
        className={`py-4 px-3 text-right text-sm tabular-nums ${locked ? "text-ink-muted" : pnlColor(holding.pnl)}`}
      >
        {locked ? (
          <Masked prefix="$" count={5} />
        ) : (
          <>
            {holding.pnl >= 0 ? "+" : ""}
            {fmt(holding.pnl)}
            <span className="text-xs ml-1 opacity-70">
              ({holding.pnl_percent >= 0 ? "+" : ""}
              {holding.pnl_percent.toFixed(2)}%)
            </span>
          </>
        )}
      </td>
      <td className="py-4 px-3 text-right text-sm text-ink-muted tabular-nums">
        {locked ? <Masked suffix="%" count={3} /> : <>{pct.toFixed(1)}%</>}
      </td>
      <td className="py-4 px-3 text-right whitespace-nowrap">
        <button
          onClick={() => onEdit(holding)}
          className="opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 text-xs text-ink-faint hover:text-accent transition-opacity"
          aria-label={`編輯 ${holding.ticker}`}
          title="編輯持股"
        >
          <Pencil size={14} aria-hidden="true" />
        </button>
        <button
          onClick={() => onDelete(holding.id)}
          className="ml-3 opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 text-xs text-ink-faint hover:text-red-400 transition-opacity"
          aria-label={`刪除 ${holding.ticker}`}
          title="刪除持股"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </td>
    </tr>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function Portfolio() {
  const [showAdd, setShowAdd] = useState(false);
  const [showTx, setShowTx] = useState(false);
  const [editing, setEditing] = useState<HoldingWithPrice | null>(null);
  const pnlLocked = usePrivacyStore((s) => s.pnlLocked);
  const toggleLock = usePrivacyStore((s) => s.toggleLock);

  const portfolioQuery = usePortfolio();
  // 交易紀錄抓不到不算整頁失敗（維持原本 .catch(() => []) 的語意）
  const transactions = usePortfolioTransactions().data ?? [];

  // 四個 mutation 的 onSuccess 會失效整個 portfolio 前綴，
  // 且 mutateAsync 會等失效後的重抓完成才 resolve —— 與原本
  // 每個 handler 手動 await fetchPortfolio() 的時序一致。
  const addHoldingMutation = useAddHolding();
  const addTransactionMutation = useAddTransaction();
  const updateHoldingMutation = useUpdateHolding();
  const deleteHoldingMutation = useDeleteHolding();

  const summary = portfolioQuery.data;

  // useCountUp 依 React hooks 規則必須在任何 early return 之前呼叫；
  // loading/error 態下 summary 為 undefined，用 0 當 fallback（畫面本身
  // 會先走下面的 isPending/error early return，不會顯示這兩個數字）。
  const totalValueDisplay = useCountUp(summary?.total_value ?? 0, {
    format: (v) => `$${fmt(v)}`,
  });
  const totalPnlDisplay = useCountUp(summary?.total_pnl ?? 0, {
    format: (v) => `${v >= 0 ? "+" : ""}$${fmt(v)}`,
  });

  const handleAdd = async (data: {
    ticker: string;
    shares: number;
    avg_cost: number;
    name: string;
    notes: string;
  }) => {
    await addHoldingMutation.mutateAsync(data);
  };

  const handleAddTransaction = async (data: AddTransactionInput) => {
    await addTransactionMutation.mutateAsync(data);
  };

  const handleEdit = async (
    holdingId: string,
    data: { shares: number; avg_cost: number; notes: string },
  ) => {
    await updateHoldingMutation.mutateAsync({ holdingId, data });
  };

  const handleDelete = async (holdingId: string) => {
    await deleteHoldingMutation.mutateAsync(holdingId);
  };

  if (portfolioQuery.isPending) {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <p className="text-sm text-ink-muted">載入投資組合中…</p>
      </div>
    );
  }

  if (portfolioQuery.error) {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <p className="text-sm text-red-400">
          {portfolioQuery.error instanceof Error
            ? portfolioQuery.error.message
            : "載入失敗"}
        </p>
      </div>
    );
  }

  const hasHoldings = summary && summary.holdings_count > 0;

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 md:mb-10">
        <div>
          <h1 className="text-2xl font-semibold text-ink-strong">投資組合</h1>
          <p className="text-sm text-ink-muted mt-1">即時市值、損益追蹤</p>
        </div>
        <div className="flex gap-2">
          {hasHoldings && (
            <button
              onClick={toggleLock}
              className="btn btn-ghost rounded-xl px-4 py-2.5 text-sm"
              title={pnlLocked ? "顯示損益與持股金額" : "隱藏損益與持股金額"}
              aria-pressed={pnlLocked}
            >
              <EyeGlyph off={pnlLocked} />
              {pnlLocked ? "顯示金額" : "隱藏金額"}
            </button>
          )}
          <button
            onClick={() => setShowTx(true)}
            className="btn btn-primary rounded-xl px-5 py-2.5 text-sm transition-opacity hover:opacity-90"
          >
            + 記錄交易
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="btn btn-ghost rounded-xl px-5 py-2.5 text-sm"
            title="不記交易明細，直接輸入現有持股與平均成本"
          >
            快速新增持股
          </button>
        </div>
      </div>

      {/* 損益 / 持股 / 交易 —— 鎖定時各金額欄位以圓點遮罩（見 Masked、locked prop） */}
      {/* Summary cards */}
      {hasHoldings && summary && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4 mb-8 md:mb-10">
          <div className="card p-5">
            <p className="text-xs text-ink-muted mb-2">總市值</p>
            <p className="text-lg font-semibold text-ink-strong tabular-nums">
              {pnlLocked ? <Masked prefix="$" /> : totalValueDisplay}
            </p>
          </div>
          <div className="card p-5">
            <p className="text-xs text-ink-muted mb-2">總成本</p>
            <p className="text-lg font-semibold text-ink tabular-nums">
              {pnlLocked ? <Masked prefix="$" /> : <>${fmt(summary.total_cost)}</>}
            </p>
          </div>
          <div
            className="card p-5"
            style={!pnlLocked ? { background: pnlBg(summary.total_pnl) } : undefined}
          >
            <p className="text-xs text-ink-muted mb-2">總損益</p>
            <p
              className={`text-lg font-semibold tabular-nums ${pnlLocked ? "text-ink-muted" : pnlColor(summary.total_pnl)}`}
            >
              {pnlLocked ? <Masked prefix="$" /> : totalPnlDisplay}
            </p>
          </div>
          <div
            className="card p-5"
            style={
              !pnlLocked ? { background: pnlBg(summary.total_pnl) } : undefined
            }
          >
            <p className="text-xs text-ink-muted mb-2">報酬率</p>
            <p
              className={`text-lg font-semibold tabular-nums ${pnlLocked ? "text-ink-muted" : pnlColor(summary.total_pnl_percent)}`}
            >
              {pnlLocked ? (
                <Masked suffix="%" count={4} />
              ) : (
                <>
                  {summary.total_pnl_percent >= 0 ? "+" : ""}
                  {summary.total_pnl_percent.toFixed(2)}%
                </>
              )}
            </p>
          </div>
          <div
            className="card p-5"
            style={
              !pnlLocked ? { background: pnlBg(summary.realized_pnl) } : undefined
            }
          >
            <p className="text-xs text-ink-muted mb-2">
              已實現損益（含費稅）
            </p>
            <p
              className={`text-lg font-semibold tabular-nums ${pnlLocked ? "text-ink-muted" : pnlColor(summary.realized_pnl)}`}
            >
              {pnlLocked ? (
                <Masked prefix="$" />
              ) : (
                <>
                  {summary.realized_pnl >= 0 ? "+" : ""}$
                  {fmt(summary.realized_pnl)}
                </>
              )}
            </p>
          </div>
        </div>
      )}

      {/* Holdings table */}
      {hasHoldings && summary ? (
        <div className="card overflow-hidden">
          <div className="px-6 py-4 border-b border-line-subtle">
            <h2 className="text-sm font-medium text-ink">
              持股明細（{summary.holdings_count} 檔）
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-xs text-ink-muted border-b border-line-subtle">
                  <th className="text-left py-3 px-4 font-medium">股票</th>
                  <th className="text-right py-3 px-3 font-medium">股數</th>
                  <th className="text-right py-3 px-3 font-medium">成本</th>
                  <th className="text-right py-3 px-3 font-medium">現價</th>
                  <th className="text-right py-3 px-3 font-medium">市值</th>
                  <th className="text-right py-3 px-3 font-medium">損益</th>
                  <th className="text-right py-3 px-3 font-medium">佔比</th>
                  <th className="w-16"></th>
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
                      locked={pnlLocked}
                      onEdit={setEditing}
                      onDelete={handleDelete}
                    />
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-16 text-center">
          <Briefcase
            className="w-10 h-10 mx-auto mb-4 text-ink-faint"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <h2 className="text-lg font-medium text-ink-strong mb-2">
            開始建立你的投資組合
          </h2>
          <p className="text-sm text-ink-muted mb-6">
            新增持股後，即可追蹤即時市值與損益
          </p>
          <button
            onClick={() => setShowAdd(true)}
            className="btn btn-primary rounded-xl px-6 py-2.5 text-sm transition-opacity hover:opacity-90"
          >
            + 新增第一筆持股
          </button>
        </div>
      )}

      {/* Transactions history */}
      {transactions.length > 0 && (
        <div className="card overflow-hidden mt-8">
          <div className="px-6 py-4 border-b border-line-subtle">
            <h2 className="text-sm font-medium text-ink">
              交易紀錄（最近 {Math.min(transactions.length, 50)} 筆）
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-xs text-ink-muted border-b border-line-subtle">
                  <th className="text-left py-3 px-4 font-medium">日期</th>
                  <th className="text-left py-3 px-3 font-medium">股票</th>
                  <th className="text-left py-3 px-3 font-medium">動作</th>
                  <th className="text-right py-3 px-3 font-medium">股數</th>
                  <th className="text-right py-3 px-3 font-medium">成交價</th>
                  <th className="text-right py-3 px-3 font-medium">費用+稅</th>
                  <th className="text-right py-3 px-3 font-medium">
                    已實現損益
                  </th>
                </tr>
              </thead>
              <tbody>
                {transactions.slice(0, 50).map((t) => (
                  <tr key={t.id} className="border-b border-line-subtle">
                    <td className="py-3 px-4 text-xs text-ink-secondary tabular-nums">
                      {t.trade_date}
                    </td>
                    <td className="py-3 px-3 text-sm text-ink-strong">
                      {t.ticker}
                      {t.name && (
                        <span className="text-xs text-ink-faint ml-1.5">
                          {t.name}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                          t.action === "buy"
                            ? "text-red-400 bg-red-400/10"
                            : "text-emerald-400 bg-emerald-400/10"
                        }`}
                      >
                        {t.action === "buy" ? "買入" : "賣出"}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right text-sm text-ink tabular-nums">
                      {pnlLocked ? <Masked count={4} /> : fmt(t.shares)}
                    </td>
                    <td className="py-3 px-3 text-right text-sm text-ink tabular-nums">
                      ${fmt(t.price, 2)}
                    </td>
                    <td className="py-3 px-3 text-right text-xs text-ink-muted tabular-nums">
                      {pnlLocked ? (
                        <Masked prefix="$" count={4} />
                      ) : (
                        <>${fmt(t.fee + t.tax, 0)}</>
                      )}
                    </td>
                    <td
                      className={`py-3 px-3 text-right text-sm tabular-nums ${
                        pnlLocked
                          ? "text-ink-muted"
                          : t.action === "sell"
                            ? pnlColor(t.realized_pnl)
                            : "text-ink-faint"
                      }`}
                    >
                      {t.action === "sell" ? (
                        pnlLocked ? (
                          <Masked prefix="$" count={5} />
                        ) : (
                          `${t.realized_pnl >= 0 ? "+" : ""}${fmt(t.realized_pnl)}`
                        )
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-xs text-ink-muted leading-relaxed mt-6 flex items-start gap-1.5">
        <TriangleAlert
          size={14}
          className="text-warn shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <span>
          損益以台股牌告費率（手續費 0.1425%、賣出證交稅
          0.3%）估算，未含券商折讓與股利；僅供參考，實際請以券商對帳單為準。
        </span>
      </p>

      {/* Add holding modal */}
      {showAdd && (
        <AddHoldingModal onClose={() => setShowAdd(false)} onAdd={handleAdd} />
      )}
      {showTx && (
        <TransactionModal
          onClose={() => setShowTx(false)}
          onSubmit={handleAddTransaction}
        />
      )}
      {editing && (
        <EditHoldingModal
          holding={editing}
          onClose={() => setEditing(null)}
          onSave={handleEdit}
        />
      )}
    </div>
  );
}
