import { useState, useEffect, useCallback, useRef, lazy, Suspense } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { TrendingUp, TriangleAlert } from "lucide-react";
import { type StockSuggestion } from "@/lib/api";
import {
  usePopularStocks,
  useStockFundamentals,
  useStockInstitutional,
  useStockMargin,
  useStockPrice,
  useStockSearch,
  useStockTechnicals,
} from "@/lib/queries/stock";
import { fmtPrice } from "@/lib/format";
import { useCountUp } from "@/lib/useCountUp";
import type { Tab, ChartPeriod } from "@/types/stock";
import {
  CHART_PERIODS,
  CHART_PERIOD_LABELS,
  INTERVAL_LABELS,
} from "@/types/stock";
import PopularStocks from "@/components/PopularStocks";
import StockOverviewTab from "@/pages/stock/StockOverviewTab";
import StockTechnicalTab from "@/pages/stock/StockTechnicalTab";
import StockFundamentalTab from "@/pages/stock/StockFundamentalTab";
import StockInstitutionalTab from "@/pages/stock/StockInstitutionalTab";
import StockNewsTab from "@/pages/stock/StockNewsTab";

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
  news: "新聞",
};

export default function Stock() {
  const { symbol: paramSymbol } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // 網址是查詢對象的單一真實來源，直接推導而不另存一份 state：
  // 瀏覽器上一頁／下一頁只會改網址，多存一份就得手動同步，同步不及時
  // 就會出現「網址已變、畫面沒動」。
  const symbol = paramSymbol ?? "";
  const activeTab = (searchParams.get("tab") as Tab) || "overview";
  const setActiveTab = (tab: Tab) =>
    setSearchParams({ tab }, { replace: true });

  const [searchInput, setSearchInput] = useState(paramSymbol ?? "");
  // 走勢圖期間；只影響圖表長度，技術指標數值不受影響（後端一律用 1y 日線計算）
  const [chartPeriod, setChartPeriod] = useState<ChartPeriod>("3mo");

  // Autocomplete state
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // 各區塊各自一個 query：切換期間只會重打技術指標，其餘區塊不重抓也不閃爍；
  // 查過的標的在 gcTime 內回頭再查是快取命中，直接秒出舊值並在背景更新。
  const priceQuery = useStockPrice(symbol);
  const technicalQuery = useStockTechnicals(symbol, chartPeriod);
  const fundamentalQuery = useStockFundamentals(symbol);
  const institutionalQuery = useStockInstitutional(symbol);
  const marginQuery = useStockMargin(symbol);
  const popularQuery = usePopularStocks(!symbol);
  const { data: suggestions = [] } = useStockSearch(debouncedQuery);

  const priceData = priceQuery.data ?? null;
  const technicalData = technicalQuery.data ?? null;
  // isLoading（而非 isPending）：快取命中時為 false，不會再閃一次「查詢中…」
  const loading = priceQuery.isLoading;
  const chartLoading = technicalQuery.isFetching;
  // 只有報價失敗才算整頁失敗；其餘區塊缺資料由各自的分頁自行呈現
  const error = priceQuery.isError
    ? "無法取得股票資料，請確認代碼是否正確"
    : "";

  const currency = priceData?.currency ?? "";
  // 現價 count-up：700ms easeOutCubic，依賴 currency 做格式化；priceData 為
  // null 時 target 為 0，但此時對應區塊未渲染（見下方 {priceData && (...)}）。
  const priceDisplay = useCountUp(priceData?.price ?? 0, {
    format: (v) => fmtPrice(v, currency),
  });

  // 回到卡片頁（網址沒有 symbol）：個股資料隨 query key 變動自然消失，
  // 這裡只需要收掉搜尋框殘留的 UI 狀態。
  // 用 React 官方的「render 期間調整 state」寫法而不是 useEffect：effect 版
  // 會先用舊值畫一幀再重畫，使用者會看到搜尋框殘留上一檔股票的名稱閃一下。
  const [prevParamSymbol, setPrevParamSymbol] = useState(paramSymbol);
  if (paramSymbol !== prevParamSymbol) {
    setPrevParamSymbol(paramSymbol);
    if (!paramSymbol) {
      setSearchInput("");
      setChartPeriod("3mo");
      setShowSuggestions(false);
    }
  }

  // Debounced autocomplete：實際的請求與快取交給 useStockSearch，
  // 這裡只負責把輸入節流成 query key。
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchInput.trim()), 300);
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

  /**
   * 前往個股頁。從熱門標的頁進入時用 push，讓瀏覽器上一頁能回到卡片頁；
   * 個股之間切換用 replace，免得連查五檔就要按五次上一頁才回得去。
   */
  const goToSymbol = useCallback(
    (ticker: string, label: string) => {
      setSearchInput(label);
      setShowSuggestions(false);
      navigate(`/stock/${encodeURIComponent(ticker)}`, {
        replace: Boolean(symbol),
      });
    },
    [navigate, symbol],
  );

  /** 回到熱門標的頁。實際的狀態清理由下方的 URL 同步 effect 負責。 */
  const backToPopular = useCallback(() => {
    navigate("/stock", { replace: true });
  }, [navigate]);

  const handleSelectSuggestion = useCallback(
    (s: StockSuggestion) => goToSymbol(s.ticker, `${s.code} ${s.name}`),
    [goToSymbol],
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = searchInput.trim();
    if (!trimmed) return;
    const sym = /^[A-Za-z$]+$/.test(trimmed) ? trimmed.toUpperCase() : trimmed;
    goToSymbol(sym, searchInput);
  };

  const isPositive = (priceData?.change ?? 0) >= 0;
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
            className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-faint pointer-events-none"
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
            onChange={(e) => {
              setSearchInput(e.target.value);
              // 建議清單改由 query 快取提供，不再隨每次抓取自動開闔，
              // 因此開啟的時機收斂成「使用者正在輸入」這一個。
              setShowSuggestions(true);
            }}
            onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            placeholder="輸入股票代號或名稱（例：2330、台積電）…"
            className="stock-search-input w-full rounded-2xl pl-11 pr-11 py-4 text-sm text-ink placeholder-ink-faint bg-surface border border-line"
          />
          {/* 清空＝回到熱門標的：此頁的「初始狀態」就是卡片頁，只清文字會停在個股頁上 */}
          {searchInput && (
            <button
              type="button"
              onClick={backToPopular}
              aria-label="清除搜尋並返回熱門標的"
              className="absolute right-3.5 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center rounded-full text-ink-faint hover:text-ink transition-colors"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          )}
          {/* Autocomplete dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <ul
              role="listbox"
              className="card absolute z-50 left-0 right-0 top-full mt-1.5 overflow-hidden"
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
                  className="flex items-center justify-between px-4 py-3 cursor-pointer transition-colors hover:bg-[var(--surface-2)]"
                >
                  <span className="text-sm text-ink">
                    <span className="font-mono font-semibold text-accent mr-2">
                      {s.code}
                    </span>
                    {s.name}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full shrink-0 bg-[var(--accent-soft)] text-accent border border-[var(--accent-soft)]">
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
          className="btn btn-primary rounded-2xl px-5 md:px-7 py-3 md:py-4 text-sm whitespace-nowrap disabled:opacity-40"
        >
          {loading ? "查詢中…" : "查詢"}
        </button>
      </form>

      {symbol && (
        <button
          onClick={backToPopular}
          className="inline-flex items-center gap-1.5 mb-6 -mt-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors text-ink-faint hover:text-ink bg-[var(--surface-2)]"
        >
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="w-3.5 h-3.5"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
              clipRule="evenodd"
            />
          </svg>
          熱門標的
        </button>
      )}

      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-8 px-5 py-4 rounded-card text-sm text-danger"
          style={{
            background: "color-mix(in srgb, var(--danger) 8%, transparent)",
            border: "1px solid color-mix(in srgb, var(--danger) 15%, transparent)",
          }}
        >
          {error}
        </div>
      )}

      {!symbol && (
        popularQuery.data ? (
          <PopularStocks data={popularQuery.data} onSelect={goToSymbol} />
        ) : (
          <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 bg-[var(--surface-2)] border border-line">
              <TrendingUp size={16} className="text-ink-muted" aria-hidden="true" />
            </div>
            <p className="text-ink-faint text-sm">輸入股票代號或公司名稱開始查詢</p>
          </div>
        )
      )}

      {priceData && (
        <>
          {/* Price header */}
          <div className="card p-7 mb-8">
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h1
                    className="text-xl font-bold text-ink-strong"
                    style={{ textWrap: "balance" }}
                  >
                    {isTW
                      ? priceData.ticker.replace(/\.(TW|TWO)$/, "")
                      : priceData.ticker}
                  </h1>
                  <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-[var(--accent-soft)] text-accent border border-[var(--accent-soft)]">
                    {marketLabel(priceData.exchange, priceData.ticker)}
                  </span>
                </div>
                <p className="text-ink-secondary text-sm mt-1">{priceData.name}</p>
              </div>
              <div className="text-right">
                <div className="text-2xl md:text-3xl font-bold text-ink-strong tracking-tight tabular-nums">
                  {priceDisplay}
                </div>
                <div
                  className={`text-sm font-medium tabular-nums mt-2 ${
                    isPositive ? "text-up" : "text-down"
                  }`}
                >
                  {isPositive ? "▲" : "▼"}{" "}
                  {Math.abs(priceData.change ?? 0).toFixed(2)} (
                  {Math.abs(priceData.change_percent ?? 0).toFixed(2)}%)
                </div>
                <p className="text-[11px] text-ink-muted mt-1.5 tabular-nums">
                  {priceData.is_intraday ? "盤中報價（可能延遲）" : "收盤資料"}
                  {priceData.as_of_date ? ` · 截至 ${priceData.as_of_date}` : ""}
                  {priceData.data_source ? ` · 來源 ${priceData.data_source}` : ""}
                </p>
              </div>
            </div>

            {/* Price chart */}
            <div className="mt-6">
              <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                <span className="text-[11px] font-semibold tracking-wide text-ink-muted">
                  收盤走勢
                  {/* 長期間會降頻，不標示的話使用者會把月線誤讀成日線 */}
                  {technicalData &&
                    technicalData.history_interval !== "1d" &&
                    `（${INTERVAL_LABELS[technicalData.history_interval] ?? technicalData.history_interval}）`}
                </span>
                <div className="flex gap-0.5 p-1 rounded-xl overflow-x-auto max-w-full bg-[var(--surface-2)] border border-line-subtle">
                  {CHART_PERIODS.map((p) => (
                    <button
                      key={p}
                      onClick={() => setChartPeriod(p)}
                      aria-pressed={chartPeriod === p}
                      className={`shrink-0 whitespace-nowrap px-2.5 py-1 rounded-lg text-[11px] font-semibold tracking-wide transition-colors ${
                        chartPeriod === p
                          ? "text-ink border border-line-strong"
                          : "text-ink-faint border border-transparent"
                      }`}
                      style={
                        chartPeriod === p
                          ? { background: "var(--accent-soft)" }
                          : undefined
                      }
                    >
                      {CHART_PERIOD_LABELS[p]}
                    </button>
                  ))}
                </div>
              </div>
              <div
                className="h-48 transition-opacity duration-200"
                style={{ opacity: chartLoading ? 0.45 : 1 }}
              >
                {technicalData && technicalData.history.length > 0 ? (
                  <Suspense
                    fallback={
                      <div className="flex items-center justify-center h-full text-xs text-ink-faint">
                        圖表載入中…
                      </div>
                    }
                  >
                    <PriceChart
                      history={technicalData.history}
                      isPositive={isPositive}
                    />
                  </Suspense>
                ) : (
                  <div className="flex items-center justify-center h-full text-xs text-ink-faint">
                    {chartLoading ? "圖表載入中…" : "查無歷史價格資料"}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="stock-tabs-wrap flex gap-1 mb-7 p-1.5 w-fit max-w-full rounded-2xl bg-[var(--surface-2)] border border-line-subtle">
            {(
              ["overview", "technical", "fundamental", "institutional", "news"] as Tab[]
            ).map(
              (tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`shrink-0 whitespace-nowrap px-6 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-colors ${
                    activeTab === tab
                      ? "text-ink border border-line-strong"
                      : "text-ink-faint border border-transparent"
                  }`}
                  style={
                    activeTab === tab
                      ? { background: "var(--accent-soft)" }
                      : undefined
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
          ) : activeTab === "fundamental" && fundamentalQuery.data ? (
            <StockFundamentalTab
              fundamentalData={fundamentalQuery.data}
              currency={currency}
              ticker={priceData.ticker}
            />
          ) : activeTab === "institutional" ? (
            <StockInstitutionalTab
              institutionalData={institutionalQuery.data ?? null}
              marginData={marginQuery.data ?? null}
              isTW={isTW}
            />
          ) : activeTab === "news" ? (
            <StockNewsTab ticker={priceData.ticker} />
          ) : (
            // 該分頁資料載入失敗時不能靜默空白，要給可行動的訊息
            <div role="alert" className="card p-8 text-center text-sm text-ink-secondary">
              此分頁資料暫時無法取得，可能是資料來源異常或該股票不支援此分析。
              請稍後重試，或改查其他分頁。
            </div>
          )}

          <p className="flex items-start gap-1.5 text-xs text-ink-muted leading-relaxed mt-6">
            <TriangleAlert
              size={14}
              className="text-warn shrink-0 mt-0.5"
              aria-hidden="true"
            />
            <span>
              本頁數據與估值僅供學習與研究用途，不構成投資建議；「便宜／合理／昂貴」為統計估算的估值帶，非目標價。資料可能延遲，交易前請以券商報價為準。
            </span>
          </p>
        </>
      )}
    </div>
  );
}
