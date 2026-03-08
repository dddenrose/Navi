import {
  useState,
  useEffect,
  useCallback,
  useRef,
  lazy,
  Suspense,
} from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  getAuthHeaders,
  getStockPrice,
  getStockTechnicals,
  getStockFundamentals,
  getStockInstitutional,
  getStockMargin,
  searchStocks,
  type StockSuggestion,
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
// yfinance 比率類欄位均為小數形式 (0.15 = 15%)—需乘 100 展示
const fmtPct = (n?: number | null) =>
  n != null ? `${numFmt.format(n * 100)}%` : "-";
const fmtPrice = (n: number | null | undefined, currency: string) => {
  if (n == null) return "-";
  const prefix = currency === "TWD" ? "NT$ " : "$";
  return `${prefix}${numFmt.format(n)}`;
};
const fmtLarge = (n?: number | null, currency = "") => {
  if (n == null) return "-";
  const prefix = currency === "TWD" ? "NT$ " : "$";
  if (n >= 1e12) return `${prefix}${numFmt.format(n / 1e12)}T`;
  if (n >= 1e9) return `${prefix}${numFmt.format(n / 1e9)}B`;
  if (n >= 1e6) return `${prefix}${numFmt.format(n / 1e6)}M`;
  return `${prefix}${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n)}`;
};

interface StockPrice {
  ticker: string;
  name: string;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  volume: number | null;
  market_cap: number | null;
  currency: string;
  exchange: string;
  high_52w: number | null;
  low_52w: number | null;
  history?: Array<{ date: string; close: number }>;
}

interface Technicals {
  ticker: string;
  period: string;
  current_price: number | null;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  ma_trend: string;
  rsi_14: number | null;
  rsi_signal: string;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  macd_cross: string;
  k_value: number | null;
  d_value: number | null;
  kd_signal: string;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  bb_position: string;
  supports: Array<[string, number]>;
  resistances: Array<[string, number]>;
  fibonacci_levels: Record<string, number>;
  swing_high: number | null;
  swing_low: number | null;
  stop_loss: number | null;
  stop_loss_note: string;
  risk_reward_note: string;
  summary: string;
}

interface InstitutionalDaily {
  date: string;
  foreign_buy: number;
  foreign_sell: number;
  foreign_net: number;
  investment_trust_buy: number;
  investment_trust_sell: number;
  investment_trust_net: number;
  dealer_buy: number;
  dealer_sell: number;
  dealer_net: number;
  total_net: number;
}

interface InstitutionalData {
  ticker: string;
  name: string;
  records: InstitutionalDaily[];
  foreign_consecutive_days: number;
  foreign_total_net: number;
  investment_trust_total_net: number;
  dealer_total_net: number;
  total_net: number;
  error: string;
}

interface MarginDailyData {
  date: string;
  margin_buy: number;
  margin_sell: number;
  margin_cash_repay: number;
  margin_balance: number;
  margin_limit: number;
  margin_utilization: number;
  short_sell: number;
  short_buy: number;
  short_cash_repay: number;
  short_balance: number;
  offset: number;
}

interface MarginData {
  ticker: string;
  name: string;
  records: MarginDailyData[];
  latest: MarginDailyData | null;
  margin_change: number;
  short_change: number;
  error: string;
}

interface Fundamentals {
  ticker: string;
  name: string;
  pe_ratio: number | null;
  forward_pe: number | null;
  pb_ratio: number | null;
  ps_ratio: number | null;
  roe: number | null;
  roa: number | null;
  profit_margin: number | null;
  operating_margin: number | null;
  revenue_growth: number | null;
  earnings_growth: number | null;
  eps: number | null;
  forward_eps: number | null;
  dividend_yield: number | null;
  cheap_price: number | null;
  fair_price: number | null;
  expensive_price: number | null;
  valuation_note: string;
  sector: string;
  industry: string;
  description: string;
}

type Tab = "overview" | "technical" | "fundamental" | "institutional";

function marketLabel(exchange: string, ticker: string): string {
  if (ticker.endsWith(".TW")) return "上市";
  if (ticker.endsWith(".TWO")) return "上櫃";
  return exchange || "股市";
}

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
  const [institutionalData, setInstitutionalData] =
    useState<InstitutionalData | null>(null);
  const [marginData, setMarginData] = useState<MarginData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Autocomplete state
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  const fetchData = useCallback(async (sym: string) => {
    setLoading(true);
    setError("");
    setPriceData(null);
    setTechnicalData(null);
    setFundamentalData(null);
    setInstitutionalData(null);
    setMarginData(null);

    try {
      // Fetch token once, share across parallel requests
      const headers = await getAuthHeaders();
      const isTWSE = sym.endsWith(".TW") || sym.endsWith(".TWO");
      const promises: [
        Promise<any>,
        Promise<any>,
        Promise<any>,
        Promise<any>,
        Promise<any>,
      ] = [
        getStockPrice(sym, headers),
        getStockTechnicals(sym, headers),
        getStockFundamentals(sym, headers),
        isTWSE ? getStockInstitutional(sym, headers) : Promise.reject("skip"),
        isTWSE ? getStockMargin(sym, headers) : Promise.reject("skip"),
      ];
      const [price, tech, fund, inst, margin] =
        await Promise.allSettled(promises);

      if (price.status === "fulfilled") setPriceData(price.value);
      else setError("無法取得股票資料，請確認代碼是否正確");

      if (tech.status === "fulfilled") setTechnicalData(tech.value);
      if (fund.status === "fulfilled") setFundamentalData(fund.value);
      if (inst.status === "fulfilled") setInstitutionalData(inst.value);
      if (margin.status === "fulfilled") setMarginData(margin.value);
    } catch {
      setError("資料載入失敗");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (symbol) fetchData(symbol);
  }, [symbol, fetchData]);

  // Debounced autocomplete: call search API as user types
  useEffect(() => {
    const trimmed = searchInput.trim();
    if (trimmed.length < 1) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await searchStocks(trimmed);
        setSuggestions(data);
        setShowSuggestions(data.length > 0);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelectSuggestion = useCallback(
    (s: StockSuggestion) => {
      setSearchInput(`${s.code} ${s.name}`);
      setShowSuggestions(false);
      setSuggestions([]);
      setSymbol(s.ticker);
      navigate(`/stock/${encodeURIComponent(s.ticker)}`, { replace: true });
    },
    [navigate],
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = searchInput.trim();
    if (!trimmed) return;
    setShowSuggestions(false);
    // Only uppercase for pure-ASCII tickers (US stocks)
    const sym = /^[A-Za-z$]+$/.test(trimmed) ? trimmed.toUpperCase() : trimmed;
    setSymbol(sym);
    navigate(`/stock/${encodeURIComponent(sym)}`, { replace: true });
  };

  const isPositive = (priceData?.change ?? 0) >= 0;
  const currency = priceData?.currency ?? "";
  const isTW =
    priceData?.ticker?.endsWith(".TW") ||
    priceData?.ticker?.endsWith(".TWO") ||
    false;

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto animate-fade-up">
      {/* Search bar */}
      <form
        onSubmit={handleSearch}
        className="flex gap-3 md:gap-4 mb-8 md:mb-10"
      >
        <div className="relative flex-1" ref={searchContainerRef}>
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
            股票代號或名稱
          </label>
          <input
            id="stock-search"
            type="text"
            name="symbol"
            autoComplete="off"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            placeholder="輸入股票代號或名稱（例：2330、台積電）…"
            className="stock-search-input w-full rounded-2xl pl-11 pr-5 py-4 text-sm text-slate-200 placeholder-slate-700"
            style={{
              background: "var(--overlay-bg)",
              border: "1px solid var(--border)",
            }}
          />
          {/* Autocomplete dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <ul
              role="listbox"
              className="absolute z-50 left-0 right-0 top-full mt-1.5 rounded-2xl overflow-hidden shadow-2xl"
              style={{
                background: "var(--card-bg)",
                border: "1px solid var(--border)",
              }}
            >
              {suggestions.map((s) => (
                <li
                  key={s.ticker}
                  role="option"
                  aria-selected={false}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelectSuggestion(s);
                  }}
                  className="flex items-center justify-between px-4 py-3 cursor-pointer transition-colors hover:bg-white/5"
                >
                  <span className="text-sm text-slate-200">
                    <span className="font-mono font-semibold text-indigo-400 mr-2">
                      {s.code}
                    </span>
                    {s.name}
                  </span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full shrink-0"
                    style={{
                      background: "rgba(99,102,241,0.12)",
                      color: "#818cf8",
                      border: "1px solid rgba(99,102,241,0.2)",
                    }}
                  >
                    {s.market}
                  </span>
                </li>
              ))}
            </ul>
          )}
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
          <p className="text-slate-600 text-sm">
            輸入股票代號或公司名稱開始查詢
          </p>
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
                    {isTW
                      ? priceData.ticker.replace(/\.(TW|TWO)$/, "")
                      : priceData.ticker}
                  </h1>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{
                      background: "rgba(99,102,241,0.15)",
                      color: "#818cf8",
                      border: "1px solid rgba(99,102,241,0.2)",
                    }}
                  >
                    {marketLabel(priceData.exchange, priceData.ticker)}
                  </span>
                </div>
                <p className="text-slate-400 text-sm mt-1">{priceData.name}</p>
              </div>
              <div className="text-right">
                <div className="text-2xl md:text-3xl font-bold text-white tracking-tight tabular-nums">
                  {fmtPrice(priceData.price, currency)}
                </div>
                <div
                  className={`text-sm font-medium tabular-nums mt-2 ${
                    isPositive ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {isPositive ? "▲" : "▼"}{" "}
                  {Math.abs(priceData.change ?? 0).toFixed(2)} (
                  {Math.abs(priceData.change_percent ?? 0).toFixed(2)}%)
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
            {(
              ["overview", "technical", "fundamental", "institutional"] as Tab[]
            ).map((tab) => (
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
                    : tab === "fundamental"
                      ? "基本面"
                      : "籌碼面"}
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
                {
                  label: "市值",
                  value: fmtLarge(priceData.market_cap, currency),
                },
                {
                  label: "52週高點",
                  value:
                    priceData.high_52w != null
                      ? fmtPrice(priceData.high_52w, currency)
                      : "-",
                },
                {
                  label: "52週低點",
                  value:
                    priceData.low_52w != null
                      ? fmtPrice(priceData.low_52w, currency)
                      : "-",
                },
              ].map(({ label, value }) => (
                // rerender-memo: StatCard is memoized
                <StatCard key={label} label={label} value={value} />
              ))}
            </div>
          ) : activeTab === "technical" && technicalData ? (
            <div className="space-y-6">
              {/* 綜合判斷 */}
              {technicalData.summary && (
                <div
                  className="rounded-2xl p-5"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-xs text-slate-500 mb-2">綜合判斷</p>
                  <p className="text-sm text-slate-300 leading-relaxed">
                    {technicalData.summary}
                  </p>
                </div>
              )}

              {/* RSI */}
              {technicalData.rsi_14 != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm text-slate-400">
                      RSI (14)
                      {technicalData.rsi_signal && (
                        <span className="ml-2 text-xs text-slate-500">
                          {technicalData.rsi_signal}
                        </span>
                      )}
                    </span>
                    <span
                      className={`text-sm font-bold ${
                        technicalData.rsi_14 > 70
                          ? "text-red-400"
                          : technicalData.rsi_14 < 30
                            ? "text-green-400"
                            : "text-slate-100"
                      }`}
                    >
                      {fmtNum(technicalData.rsi_14)}
                    </span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-[width] ${
                        technicalData.rsi_14 > 70
                          ? "bg-red-400"
                          : technicalData.rsi_14 < 30
                            ? "bg-green-400"
                            : "bg-indigo-400"
                      }`}
                      style={{
                        width: `${Math.min(technicalData.rsi_14, 100)}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-slate-600 mt-2">
                    <span>超賣 &lt;30</span>
                    <span>超買 &gt;70</span>
                  </div>
                </div>
              )}

              {/* MACD */}
              {technicalData.macd != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex justify-between items-center mb-4">
                    <p className="text-sm text-slate-400">MACD</p>
                    {technicalData.macd_cross && (
                      <span className="text-xs text-slate-500">
                        {technicalData.macd_cross}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-3 md:gap-5">
                    {[
                      { label: "DIF", value: fmtNum(technicalData.macd) },
                      {
                        label: "DEA",
                        value: fmtNum(technicalData.macd_signal),
                      },
                      {
                        label: "Histogram",
                        value: fmtNum(technicalData.macd_histogram),
                        color:
                          (technicalData.macd_histogram ?? 0) >= 0
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

              {/* KD */}
              {technicalData.k_value != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex justify-between items-center mb-4">
                    <p className="text-sm text-slate-400">KD 指標</p>
                    {technicalData.kd_signal && (
                      <span className="text-xs text-slate-500">
                        {technicalData.kd_signal}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3 md:gap-5">
                    {[
                      { label: "K 值", value: fmtNum(technicalData.k_value) },
                      { label: "D 值", value: fmtNum(technicalData.d_value) },
                    ].map(({ label, value }) => (
                      <div key={label}>
                        <p className="text-xs text-slate-500">{label}</p>
                        <p className="text-sm font-semibold mt-2 text-slate-100">
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
                <div className="flex justify-between items-center mb-4">
                  <p className="text-sm text-slate-400">均線</p>
                  {technicalData.ma_trend && (
                    <span className="text-xs text-slate-500">
                      {technicalData.ma_trend}
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
                  {[
                    { label: "MA5", value: technicalData.ma5 },
                    { label: "MA10", value: technicalData.ma10 },
                    { label: "MA20", value: technicalData.ma20 },
                    { label: "MA60", value: technicalData.ma60 },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-xs text-slate-500">{label}</p>
                      <p
                        className={`text-sm font-semibold mt-2 ${
                          value != null && (priceData.price ?? 0) > value
                            ? "text-green-400"
                            : value != null
                              ? "text-red-400"
                              : "text-slate-500"
                        }`}
                      >
                        {value != null ? fmtNum(value) : "-"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Bollinger Bands */}
              {technicalData.bb_upper != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex justify-between items-center mb-4">
                    <p className="text-sm text-slate-400">布林通道</p>
                    {technicalData.bb_position && (
                      <span className="text-xs text-slate-500">
                        {technicalData.bb_position}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-3 md:gap-5">
                    {[
                      { label: "上軌", value: fmtNum(technicalData.bb_upper) },
                      {
                        label: "中軌",
                        value: fmtNum(technicalData.bb_middle),
                      },
                      { label: "下軌", value: fmtNum(technicalData.bb_lower) },
                    ].map(({ label, value }) => (
                      <div key={label}>
                        <p className="text-xs text-slate-500">{label}</p>
                        <p className="text-sm font-semibold mt-2 text-slate-100">
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* RSI Chart */}
              {technicalData.rsi_14 != null && (
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
                    <RsiChart rsi={technicalData.rsi_14} />
                  </Suspense>
                </div>
              )}

              {/* Support / Resistance */}
              {((technicalData.supports?.length ?? 0) > 0 ||
                (technicalData.resistances?.length ?? 0) > 0) && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-sm text-slate-400 mb-4">支撐 / 阻力</p>
                  <div className="grid grid-cols-2 gap-6">
                    {/* Supports */}
                    <div>
                      <p className="text-xs text-green-400 mb-3">支撐位</p>
                      {technicalData.supports?.length ? (
                        <div className="space-y-2">
                          {technicalData.supports.map(([label, val]) => (
                            <div
                              key={label}
                              className="flex justify-between text-sm"
                            >
                              <span className="text-slate-500">{label}</span>
                              <span className="text-green-400 font-semibold tabular-nums">
                                {fmtNum(val)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-600">-</p>
                      )}
                    </div>
                    {/* Resistances */}
                    <div>
                      <p className="text-xs text-red-400 mb-3">阻力位</p>
                      {technicalData.resistances?.length ? (
                        <div className="space-y-2">
                          {technicalData.resistances.map(([label, val]) => (
                            <div
                              key={label}
                              className="flex justify-between text-sm"
                            >
                              <span className="text-slate-500">{label}</span>
                              <span className="text-red-400 font-semibold tabular-nums">
                                {fmtNum(val)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-600">-</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Fibonacci Levels */}
              {technicalData.fibonacci_levels &&
                Object.keys(technicalData.fibonacci_levels).length > 0 && (
                  <div
                    className="rounded-2xl p-6"
                    style={{
                      background: "var(--card-bg)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div className="flex justify-between items-center mb-4">
                      <p className="text-sm text-slate-400">費波那契回檔</p>
                      <span className="text-xs text-slate-600">
                        高 {fmtNum(technicalData.swing_high)} / 低{" "}
                        {fmtNum(technicalData.swing_low)}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {Object.entries(technicalData.fibonacci_levels).map(
                        ([level, val]) => (
                          <div key={level}>
                            <p className="text-xs text-slate-500">{level}</p>
                            <p className="text-sm font-semibold mt-1 text-amber-400 tabular-nums">
                              {fmtNum(val)}
                            </p>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                )}

              {/* Stop Loss & Risk/Reward */}
              {technicalData.stop_loss != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-sm text-slate-400 mb-4">
                    停損建議 / 風報比
                  </p>
                  <div className="grid grid-cols-2 gap-5 mb-4">
                    <div>
                      <p className="text-xs text-slate-500">建議停損價</p>
                      <p className="text-lg font-bold text-red-400 mt-1 tabular-nums">
                        {fmtNum(technicalData.stop_loss)}
                      </p>
                    </div>
                    {technicalData.current_price != null && (
                      <div>
                        <p className="text-xs text-slate-500">距目前價差</p>
                        <p className="text-lg font-bold text-slate-200 mt-1 tabular-nums">
                          {(
                            ((technicalData.stop_loss -
                              technicalData.current_price) /
                              technicalData.current_price) *
                            100
                          ).toFixed(2)}
                          %
                        </p>
                      </div>
                    )}
                  </div>
                  {technicalData.stop_loss_note && (
                    <p className="text-xs text-slate-500 leading-relaxed mb-2">
                      {technicalData.stop_loss_note}
                    </p>
                  )}
                  {technicalData.risk_reward_note && (
                    <p className="text-xs text-slate-500 leading-relaxed">
                      {technicalData.risk_reward_note}
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : activeTab === "fundamental" && fundamentalData ? (
            <div className="space-y-6">
              {/* 公司簡介 */}
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

              {/* 估值指標 */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
                {[
                  {
                    label: "本益比 (P/E)",
                    value: fmtNum(fundamentalData.pe_ratio),
                  },
                  {
                    label: "預期本益比",
                    value: fmtNum(fundamentalData.forward_pe),
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
                    label: "EPS (TTM)",
                    value:
                      fundamentalData.eps != null
                        ? fmtNum(fundamentalData.eps)
                        : "-",
                  },
                  {
                    label: "預期 EPS",
                    value:
                      fundamentalData.forward_eps != null
                        ? fmtNum(fundamentalData.forward_eps)
                        : "-",
                  },
                  { label: "ROE", value: fmtPct(fundamentalData.roe) },
                  { label: "ROA", value: fmtPct(fundamentalData.roa) },
                  {
                    label: "淨利率",
                    value: fmtPct(fundamentalData.profit_margin),
                  },
                  {
                    label: "營業利益率",
                    value: fmtPct(fundamentalData.operating_margin),
                  },
                  {
                    label: "營收成長",
                    value: fmtPct(fundamentalData.revenue_growth),
                  },
                  {
                    label: "獲利成長",
                    value: fmtPct(fundamentalData.earnings_growth),
                  },
                ].map(({ label, value }) => (
                  <StatCard
                    key={label}
                    label={label}
                    value={value}
                    valueColor="text-slate-100"
                  />
                ))}
              </div>

              {/* 合理價位估算 */}
              {fundamentalData.fair_price != null && (
                <div
                  className="rounded-2xl p-6"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-xs text-slate-500 mb-4">
                    合理價位估算（PE 法）
                  </p>
                  <div className="grid grid-cols-3 gap-4">
                    {[
                      {
                        label: "🟢 便宜價",
                        value:
                          fundamentalData.cheap_price != null
                            ? fmtPrice(fundamentalData.cheap_price, currency)
                            : "-",
                        color: "text-green-400",
                      },
                      {
                        label: "🟡 合理價",
                        value: fmtPrice(fundamentalData.fair_price, currency),
                        color: "text-yellow-400",
                      },
                      {
                        label: "🔴 昂貴價",
                        value:
                          fundamentalData.expensive_price != null
                            ? fmtPrice(
                                fundamentalData.expensive_price,
                                currency,
                              )
                            : "-",
                        color: "text-red-400",
                      },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="text-center">
                        <p className="text-xs text-slate-500 mb-2">{label}</p>
                        <p className={`text-base font-bold ${color}`}>
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                  {fundamentalData.valuation_note && (
                    <p className="text-xs text-slate-600 mt-4 leading-relaxed">
                      {fundamentalData.valuation_note}
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : activeTab === "institutional" ? (
            <div className="space-y-6">
              {/* 法人買賣超 */}
              {institutionalData && !institutionalData.error ? (
                <>
                  {/* 法人匯總 Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                      {
                        label: "外資合計",
                        value: institutionalData.foreign_total_net,
                        extra: institutionalData.foreign_consecutive_days
                          ? `連續${Math.abs(institutionalData.foreign_consecutive_days)}天${institutionalData.foreign_consecutive_days > 0 ? "買超" : "賣超"}`
                          : undefined,
                      },
                      {
                        label: "投信合計",
                        value: institutionalData.investment_trust_total_net,
                      },
                      {
                        label: "自營商合計",
                        value: institutionalData.dealer_total_net,
                      },
                      {
                        label: "三大法人合計",
                        value: institutionalData.total_net,
                      },
                    ].map(({ label, value, extra }) => (
                      <div
                        key={label}
                        className="rounded-2xl p-5"
                        style={{
                          background: "var(--card-bg)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        <p className="text-xs text-slate-500 mb-2">{label}</p>
                        <p
                          className={`text-base font-bold tabular-nums ${
                            value > 0
                              ? "text-red-400"
                              : value < 0
                                ? "text-green-400"
                                : "text-slate-300"
                          }`}
                        >
                          {value > 0 ? "+" : ""}
                          {value.toLocaleString()} 張
                        </p>
                        {extra && (
                          <p className="text-xs text-slate-500 mt-1">{extra}</p>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* 逐日明細 */}
                  {institutionalData.records.length > 0 && (
                    <div
                      className="rounded-2xl overflow-hidden"
                      style={{
                        background: "var(--card-bg)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <p className="text-sm text-slate-400 px-6 pt-5 pb-3">
                        法人逐日買賣超（張）
                      </p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-slate-500 border-b border-white/5">
                              <th className="text-left px-4 py-2.5 font-medium">
                                日期
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                外資
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                投信
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                自營商
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                合計
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {institutionalData.records.map((r) => (
                              <tr
                                key={r.date}
                                className="border-b border-white/5 hover:bg-white/[0.02]"
                              >
                                <td className="px-4 py-2.5 text-slate-400">
                                  {r.date}
                                </td>
                                {[
                                  r.foreign_net,
                                  r.investment_trust_net,
                                  r.dealer_net,
                                  r.total_net,
                                ].map((v, i) => (
                                  <td
                                    key={i}
                                    className={`px-4 py-2.5 text-right tabular-nums font-medium ${
                                      v > 0
                                        ? "text-red-400"
                                        : v < 0
                                          ? "text-green-400"
                                          : "text-slate-500"
                                    }`}
                                  >
                                    {v > 0 ? "+" : ""}
                                    {v.toLocaleString()}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : institutionalData?.error ? (
                <div
                  className="rounded-2xl p-6 text-center"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-sm text-slate-500">
                    {institutionalData.error}
                  </p>
                </div>
              ) : !isTW ? (
                <div
                  className="rounded-2xl p-6 text-center"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-sm text-slate-500">
                    籌碼面資料僅支援台股（上市/上櫃）
                  </p>
                </div>
              ) : null}

              {/* 融資融券 */}
              {marginData && !marginData.error ? (
                <>
                  <div
                    className="rounded-2xl p-6"
                    style={{
                      background: "var(--card-bg)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    <p className="text-sm text-slate-400 mb-4">融資融券概況</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {[
                        {
                          label: "融資餘額",
                          value: marginData.latest?.margin_balance,
                          suffix: "張",
                        },
                        {
                          label: "融資增減",
                          value: marginData.margin_change,
                          suffix: "張",
                          colored: true,
                        },
                        {
                          label: "融券餘額",
                          value: marginData.latest?.short_balance,
                          suffix: "張",
                        },
                        {
                          label: "融券增減",
                          value: marginData.short_change,
                          suffix: "張",
                          colored: true,
                        },
                      ].map(({ label, value, suffix, colored }) => (
                        <div key={label}>
                          <p className="text-xs text-slate-500">{label}</p>
                          <p
                            className={`text-sm font-semibold mt-2 tabular-nums ${
                              colored
                                ? (value ?? 0) > 0
                                  ? "text-red-400"
                                  : (value ?? 0) < 0
                                    ? "text-green-400"
                                    : "text-slate-300"
                                : "text-slate-100"
                            }`}
                          >
                            {value != null
                              ? `${colored && value > 0 ? "+" : ""}${value.toLocaleString()} ${suffix}`
                              : "-"}
                          </p>
                        </div>
                      ))}
                    </div>
                    {marginData.latest?.margin_utilization != null && (
                      <div className="mt-5">
                        <div className="flex justify-between text-xs mb-2">
                          <span className="text-slate-500">融資使用率</span>
                          <span className="text-slate-300 font-medium">
                            {marginData.latest.margin_utilization.toFixed(1)}%
                          </span>
                        </div>
                        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-amber-400 transition-[width]"
                            style={{
                              width: `${Math.min(marginData.latest.margin_utilization, 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 融資融券逐日明細 */}
                  {marginData.records.length > 0 && (
                    <div
                      className="rounded-2xl overflow-hidden"
                      style={{
                        background: "var(--card-bg)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <p className="text-sm text-slate-400 px-6 pt-5 pb-3">
                        融資融券逐日明細
                      </p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-slate-500 border-b border-white/5">
                              <th className="text-left px-4 py-2.5 font-medium">
                                日期
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                融資買
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                融資賣
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                融資餘額
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                融券賣
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                融券買
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                融券餘額
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                資券互抵
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {marginData.records.map((r) => (
                              <tr
                                key={r.date}
                                className="border-b border-white/5 hover:bg-white/[0.02]"
                              >
                                <td className="px-4 py-2.5 text-slate-400">
                                  {r.date}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                                  {r.margin_buy.toLocaleString()}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                                  {r.margin_sell.toLocaleString()}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-100 font-medium">
                                  {r.margin_balance.toLocaleString()}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                                  {r.short_sell.toLocaleString()}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                                  {r.short_buy.toLocaleString()}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-100 font-medium">
                                  {r.short_balance.toLocaleString()}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">
                                  {r.offset.toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : marginData?.error ? (
                <div
                  className="rounded-2xl p-6 text-center"
                  style={{
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <p className="text-sm text-slate-500">{marginData.error}</p>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
