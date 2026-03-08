import { useState, useEffect, useCallback, useRef, lazy, Suspense } from "react";
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
import { fmtPrice } from "@/lib/format";
import type {
  StockPrice,
  Technicals,
  Fundamentals,
  InstitutionalData,
  MarginData,
  Tab,
} from "@/types/stock";
import StockOverviewTab from "@/pages/stock/StockOverviewTab";
import StockTechnicalTab from "@/pages/stock/StockTechnicalTab";
import StockFundamentalTab from "@/pages/stock/StockFundamentalTab";
import StockInstitutionalTab from "@/pages/stock/StockInstitutionalTab";

// bundle-dynamic-imports: defer ~240 kB recharts until chart is visible
const PriceChart = lazy(() => import("@/components/PriceChart"));

function marketLabel(exchange: string, ticker: string): string {
  if (ticker.endsWith(".TW")) return "上市";
  if (ticker.endsWith(".TWO")) return "上櫃";
  return exchange || "股市";
}

const TAB_LABELS: Record<Tab, string> = {
  overview: "概覽",
  technical: "技術分析",
  fundamental: "基本面",
  institutional: "籌碼面",
};

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
  const [fundamentalData, setFundamentalData] = useState<Fundamentals | null>(null);
  const [institutionalData, setInstitutionalData] = useState<InstitutionalData | null>(null);
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
      // Fetch token once, share across parallel requests (async-parallel)
      const headers = await getAuthHeaders();
      const isTWSE = sym.endsWith(".TW") || sym.endsWith(".TWO");
      const promises: [
        Promise<StockPrice>,
        Promise<Technicals>,
        Promise<Fundamentals>,
        Promise<InstitutionalData>,
        Promise<MarginData>,
      ] = [
        getStockPrice(sym, headers),
        getStockTechnicals(sym, headers),
        getStockFundamentals(sym, headers),
        isTWSE ? getStockInstitutional(sym, headers) : Promise.reject("skip"),
        isTWSE ? getStockMargin(sym, headers) : Promise.reject("skip"),
      ];
      const [price, tech, fund, inst, margin] = await Promise.allSettled(promises);

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

  // Debounced autocomplete
  useEffect(() => {
    const trimmed = searchInput.trim();
    if (trimmed.length < 1) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    const timer = setTimeout(async () => {
      const data = await searchStocks(trimmed);
      setSuggestions(data);
      setShowSuggestions(data.length > 0);
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
      <form onSubmit={handleSearch} className="flex gap-3 md:gap-4 mb-8 md:mb-10">
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
          <p className="text-slate-600 text-sm">輸入股票代號或公司名稱開始查詢</p>
        </div>
      )}

      {priceData && (
        <>
          {/* Price header */}
          <div
            className="rounded-2xl p-7 mb-8"
            style={{ background: "var(--card-bg)", border: "1px solid var(--border)" }}
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
                  <PriceChart history={priceData.history} isPositive={isPositive} />
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
            {(["overview", "technical", "fundamental", "institutional"] as Tab[]).map(
              (tab) => (
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
                  {TAB_LABELS[tab]}
                </button>
              ),
            )}
          </div>

          {/* Tab content */}
          {activeTab === "overview" ? (
            <StockOverviewTab priceData={priceData} currency={currency} />
          ) : activeTab === "technical" && technicalData ? (
            <StockTechnicalTab technicalData={technicalData} priceData={priceData} />
          ) : activeTab === "fundamental" && fundamentalData ? (
            <StockFundamentalTab fundamentalData={fundamentalData} currency={currency} />
          ) : activeTab === "institutional" ? (
            <StockInstitutionalTab
              institutionalData={institutionalData}
              marginData={marginData}
              isTW={isTW}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
