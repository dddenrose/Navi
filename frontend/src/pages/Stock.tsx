import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  getAuthHeaders,
  getStockPrice,
  getStockTechnicals,
  getStockFundamentals,
} from "@/lib/api";
import StatCard from "@/components/StatCard";

// bundle-dynamic-imports: defer ~240 kB recharts until chart is visible
const RsiChart = lazy(() => import("@/components/RsiChart"));
const PriceChart = lazy(() => import("@/components/PriceChart"));

// rendering-hoist-jsx: pure utility functions hoisted to module level
const numFmt = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const fmtNum = (n?: number | null) => (n != null ? numFmt.format(n) : "-");
const fmtPct = (n?: number | null) =>
  n != null ? `${numFmt.format(n)}%` : "-";
const fmtLarge = (n?: number | null) => {
  if (n == null) return "-";
  if (n >= 1e12) return `$${numFmt.format(n / 1e12)}T`;
  if (n >= 1e9) return `$${numFmt.format(n / 1e9)}B`;
  if (n >= 1e6) return `$${numFmt.format(n / 1e6)}M`;
  return `$${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n)}`;
};

interface StockPrice {
  symbol: string;
  company_name: string;
  current_price: number;
  previous_close: number;
  change: number;
  change_percent: number;
  volume: number;
  market_cap: number;
  high_52w: number;
  low_52w: number;
  history?: Array<{ date: string; close: number }>;
}

interface Technicals {
  symbol: string;
  rsi?: number;
  macd?: { macd: number; signal: number; histogram: number };
  sma_20?: number;
  sma_50?: number;
  sma_200?: number;
  ema_12?: number;
  ema_26?: number;
}

interface Fundamentals {
  symbol: string;
  pe_ratio?: number;
  pb_ratio?: number;
  dividend_yield?: number;
  eps?: number;
  revenue?: number;
  gross_margin?: number;
  debt_to_equity?: number;
  roe?: number;
  sector?: string;
  industry?: string;
  description?: string;
}

type Tab = "overview" | "technical" | "fundamental";

export default function Stock() {
  const { symbol: paramSymbol } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [searchInput, setSearchInput] = useState(paramSymbol ?? "");
  const [symbol, setSymbol] = useState(paramSymbol ?? "");
  const activeTab = (searchParams.get("tab") as Tab) || "overview";
  const setActiveTab = (tab: Tab) =>
    setSearchParams({ tab }, { replace: true });

  const [priceData, setPriceData] = useState<StockPrice | null>(null);
  const [technicalData, setTechnicalData] = useState<Technicals | null>(null);
  const [fundamentalData, setFundamentalData] = useState<Fundamentals | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchData = useCallback(async (sym: string) => {
    setLoading(true);
    setError("");
    setPriceData(null);
    setTechnicalData(null);
    setFundamentalData(null);

    try {
      // Fetch token once, share across parallel requests
      const headers = await getAuthHeaders();
      const [price, tech, fund] = await Promise.allSettled([
        getStockPrice(sym, headers),
        getStockTechnicals(sym, headers),
        getStockFundamentals(sym, headers),
      ]);

      if (price.status === "fulfilled") setPriceData(price.value);
      else setError("無法取得股票資料，請確認股票代號");

      if (tech.status === "fulfilled") setTechnicalData(tech.value);
      if (fund.status === "fulfilled") setFundamentalData(fund.value);
    } catch {
      setError("資料載入失敗");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (symbol) fetchData(symbol);
  }, [symbol, fetchData]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const upper = searchInput.trim().toUpperCase();
    if (!upper) return;
    setSymbol(upper);
    navigate(`/stock/${upper}`, { replace: true });
  };

  // rerender-simple-expression-in-memo: trivial boolean, no memo needed
  const isPositive = (priceData?.change ?? 0) >= 0;

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto animate-fade-up">
      {/* Search bar */}
      <form
        onSubmit={handleSearch}
        className="flex gap-3 md:gap-4 mb-8 md:mb-10"
      >
        <div className="relative flex-1">
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 pointer-events-none"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
              clipRule="evenodd"
            />
          </svg>
          <label htmlFor="stock-search" className="sr-only">
            股票代號
          </label>
          <input
            id="stock-search"
            type="text"
            name="symbol"
            autoComplete="off"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
            placeholder="輸入股票代號（例：AAPL, TSLA, NVDA）…"
            className="stock-search-input w-full rounded-2xl pl-11 pr-5 py-4 text-sm text-slate-200 placeholder-slate-700"
            style={{
              background: "var(--overlay-bg)",
              border: "1px solid var(--border)",
            }}
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="rounded-2xl px-5 md:px-7 py-3 md:py-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40 whitespace-nowrap"
          style={{
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            boxShadow: loading ? "none" : "0 4px 16px rgba(99,102,241,0.3)",
          }}
        >
          {loading ? "查詢中…" : "查詢"}
        </button>
      </form>

      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-8 px-5 py-4 rounded-2xl text-sm text-red-300"
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.15)",
          }}
        >
          {error}
        </div>
      )}

      {!symbol && !loading && (
        <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center text-3xl mb-5"
            style={{
              background: "var(--overlay-bg)",
              border: "1px solid var(--border)",
            }}
          >
            📈
          </div>
          <p className="text-slate-600 text-sm">輸入股票代號開始查詢</p>
        </div>
      )}

      {priceData && (
        <>
          {/* Price header */}
          <div
            className="rounded-2xl p-7 mb-8"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h1
                    className="text-xl font-bold text-white"
                    style={{ textWrap: "balance" }}
                  >
                    {priceData.symbol}
                  </h1>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{
                      background: "rgba(99,102,241,0.15)",
                      color: "#818cf8",
                      border: "1px solid rgba(99,102,241,0.2)",
                    }}
                  >
                    NASDAQ
                  </span>
                </div>
                <p className="text-slate-400 text-sm mt-1">
                  {priceData.company_name}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl md:text-3xl font-bold text-white tracking-tight tabular-nums">
                  ${fmtNum(priceData.current_price)}
                </div>
                <div
                  className={`text-sm font-medium tabular-nums mt-2 ${
                    isPositive ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {isPositive ? "▲" : "▼"}{" "}
                  {Math.abs(priceData.change).toFixed(2)} (
                  {Math.abs(priceData.change_percent).toFixed(2)}%)
                </div>
              </div>
            </div>

            {/* Price chart */}
            {priceData.history && priceData.history.length > 0 && (
              <div className="mt-6 h-48">
                <Suspense
                  fallback={
                    <div className="flex items-center justify-center h-full text-xs text-slate-600">
                      圖表載入中…
                    </div>
                  }
                >
                  <PriceChart
                    history={priceData.history}
                    isPositive={isPositive}
                  />
                </Suspense>
              </div>
            )}
          </div>

          {/* Tabs */}
          <div
            className="flex gap-1 mb-7 p-1.5 w-fit rounded-2xl"
            style={{
              background: "var(--overlay-bg)",
              border: "1px solid var(--border)",
            }}
          >
            {(["overview", "technical", "fundamental"] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="px-6 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-colors"
                style={
                  activeTab === tab
                    ? {
                        background:
                          "linear-gradient(135deg, rgba(99,102,241,0.3), rgba(139,92,246,0.2))",
                        border: "1px solid rgba(99,102,241,0.3)",
                        color: "var(--text-secondary)",
                      }
                    : {
                        color: "var(--text-dim)",
                        border: "1px solid transparent",
                      }
                }
              >
                {tab === "overview"
                  ? "概覽"
                  : tab === "technical"
                    ? "技術分析"
                    : "基本面"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === "overview" ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
              {[
                {
                  label: "成交量",
                  value: priceData.volume?.toLocaleString() ?? "-",
                },
                { label: "市值", value: fmtLarge(priceData.market_cap) },
                { label: "52週高點", value: `$${fmtNum(priceData.high_52w)}` },
                { label: "52週低點", value: `$${fmtNum(priceData.low_52w)}` },
              ].map(({ label, value }) => (
                // rerender-memo: StatCard is memoized
                <StatCard key={label} label={label} value={value} />
              ))}
            </div>
          ) : activeTab === "technical" && technicalData ? (
            <div className="space-y-6">
              {/* RSI */}
              {technicalData.rsi != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm text-slate-400">RSI (14)</span>
                    <span
                      className={`text-sm font-bold ${
                        technicalData.rsi > 70
                          ? "text-red-400"
                          : technicalData.rsi < 30
                            ? "text-green-400"
                            : "text-slate-100"
                      }`}
                    >
                      {fmtNum(technicalData.rsi)}
                    </span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-[width] ${
                        technicalData.rsi > 70
                          ? "bg-red-400"
                          : technicalData.rsi < 30
                            ? "bg-green-400"
                            : "bg-indigo-400"
                      }`}
                      style={{ width: `${Math.min(technicalData.rsi, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-slate-600 mt-2">
                    <span>超賣 &lt;30</span>
                    <span>超買 &gt;70</span>
                  </div>
                </div>
              )}

              {/* MACD */}
              {technicalData.macd && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-sm text-slate-400 mb-4">MACD</p>
                  <div className="grid grid-cols-3 gap-3 md:gap-5">
                    {[
                      { label: "MACD", value: fmtNum(technicalData.macd.macd) },
                      {
                        label: "Signal",
                        value: fmtNum(technicalData.macd.signal),
                      },
                      {
                        label: "Histogram",
                        value: fmtNum(technicalData.macd.histogram),
                        color:
                          (technicalData.macd.histogram ?? 0) >= 0
                            ? "text-green-400"
                            : "text-red-400",
                      },
                    ].map(({ label, value, color }) => (
                      <div key={label}>
                        <p className="text-xs text-slate-500">{label}</p>
                        <p
                          className={`text-sm font-semibold mt-2 ${color ?? "text-slate-100"}`}
                        >
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Moving Averages */}
              <div
                className="rounded-2xl p-6"
                style={{
                  background: "var(--card-bg)",
                  border: "1px solid var(--border)",
                }}
              >
                <p className="text-sm text-slate-400 mb-4">移動平均線</p>
                <div className="grid grid-cols-3 gap-3 md:gap-5">
                  {[
                    { label: "SMA 20", value: technicalData.sma_20 },
                    { label: "SMA 50", value: technicalData.sma_50 },
                    { label: "SMA 200", value: technicalData.sma_200 },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-xs text-slate-500">{label}</p>
                      <p
                        className={`text-sm font-semibold mt-2 ${
                          value != null && priceData.current_price > value
                            ? "text-green-400"
                            : "text-red-400"
                        }`}
                      >
                        ${fmtNum(value)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* RSI Chart Mock (simplified bar) */}
              {technicalData.rsi != null && (
                <div
                  className="rounded-2xl p-6 h-52"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-xs text-slate-500 mb-3">RSI 視覺化</p>
                  <Suspense
                    fallback={
                      <div className="flex items-center justify-center h-full text-xs text-slate-600">
                        圖表載入中…
                      </div>
                    }
                  >
                    <RsiChart rsi={technicalData.rsi} />
                  </Suspense>
                </div>
              )}
            </div>
          ) : activeTab === "fundamental" && fundamentalData ? (
            <div className="space-y-6">
              {fundamentalData.description && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-xs text-slate-500 mb-3">公司簡介</p>
                  <p className="text-sm text-slate-300 leading-loose line-clamp-4">
                    {fundamentalData.description}
                  </p>
                  {(fundamentalData.sector || fundamentalData.industry) && (
                    <div className="flex gap-3 mt-5">
                      {fundamentalData.sector && (
                        <span className="px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs rounded-full">
                          {fundamentalData.sector}
                        </span>
                      )}
                      {fundamentalData.industry && (
                        <span className="px-3 py-1.5 bg-slate-700 text-slate-400 text-xs rounded-full">
                          {fundamentalData.industry}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
                {[
                  {
                    label: "本益比 (P/E)",
                    value: fmtNum(fundamentalData.pe_ratio),
                  },
                  {
                    label: "股價淨值比 (P/B)",
                    value: fmtNum(fundamentalData.pb_ratio),
                  },
                  {
                    label: "殖利率",
                    value: fmtPct(fundamentalData.dividend_yield),
                  },
                  {
                    label: "EPS",
                    value:
                      fundamentalData.eps != null
                        ? `$${fmtNum(fundamentalData.eps)}`
                        : "-",
                  },
                  {
                    label: "毛利率",
                    value: fmtPct(fundamentalData.gross_margin),
                  },
                  {
                    label: "負債比",
                    value: fmtNum(fundamentalData.debt_to_equity),
                  },
                  { label: "ROE", value: fmtPct(fundamentalData.roe) },
                  { label: "營收", value: fmtLarge(fundamentalData.revenue) },
                ].map(({ label, value }) => (
                  <StatCard
                    key={label}
                    label={label}
                    value={value}
                    valueColor="text-slate-100"
                  />
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
