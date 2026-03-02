import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import {
  getStockPrice,
  getStockTechnicals,
  getStockFundamentals,
} from "@/lib/api";

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

  const [searchInput, setSearchInput] = useState(paramSymbol ?? "");
  const [symbol, setSymbol] = useState(paramSymbol ?? "");
  const [activeTab, setActiveTab] = useState<Tab>("overview");

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
      const [price, tech, fund] = await Promise.allSettled([
        getStockPrice(sym),
        getStockTechnicals(sym),
        getStockFundamentals(sym),
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

  const fmtNum = (n?: number | null, decimals = 2) =>
    n != null ? n.toFixed(decimals) : "-";
  const fmtPct = (n?: number | null) => (n != null ? `${n.toFixed(2)}%` : "-");
  const fmtLarge = (n?: number | null) => {
    if (n == null) return "-";
    if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
    if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
    return `$${n.toFixed(0)}`;
  };

  const isPositive = (priceData?.change ?? 0) >= 0;

  return (
    <div className="p-6 max-w-5xl">
      {/* Search bar */}
      <form onSubmit={handleSearch} className="flex gap-3 mb-6">
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
          placeholder="輸入股票代號 (例: AAPL, TSLA, NVDA)"
          className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl px-5 py-2.5 text-sm font-medium transition-colors"
        >
          {loading ? "查詢中..." : "查詢"}
        </button>
      </form>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
          {error}
        </div>
      )}

      {!symbol && !loading && (
        <div className="text-center py-16 text-slate-500">
          <div className="text-4xl mb-3">📈</div>
          <p>輸入股票代號開始查詢</p>
        </div>
      )}

      {priceData && (
        <>
          {/* Price header */}
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5 mb-4">
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div>
                <h1 className="text-2xl font-bold text-white">
                  {priceData.symbol}
                </h1>
                <p className="text-slate-400 text-sm">
                  {priceData.company_name}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-white">
                  ${fmtNum(priceData.current_price)}
                </div>
                <div
                  className={`text-sm font-medium ${isPositive ? "text-green-400" : "text-red-400"}`}
                >
                  {isPositive ? "▲" : "▼"}{" "}
                  {Math.abs(priceData.change).toFixed(2)} (
                  {Math.abs(priceData.change_percent).toFixed(2)}%)
                </div>
              </div>
            </div>

            {/* Price chart */}
            {priceData.history && priceData.history.length > 0 && (
              <div className="mt-4 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={priceData.history}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      tickLine={false}
                      axisLine={false}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#1e293b",
                        border: "1px solid #334155",
                        borderRadius: "8px",
                      }}
                      labelStyle={{ color: "#94a3b8", fontSize: "11px" }}
                      itemStyle={{ color: "#818cf8", fontSize: "12px" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="close"
                      stroke={isPositive ? "#4ade80" : "#f87171"}
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-4 bg-slate-800 border border-slate-700 rounded-xl p-1 w-fit">
            {(["overview", "technical", "fundamental"] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === tab
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
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
          {activeTab === "overview" && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                {
                  label: "成交量",
                  value: priceData.volume?.toLocaleString() ?? "-",
                },
                { label: "市值", value: fmtLarge(priceData.market_cap) },
                { label: "52週高點", value: `$${fmtNum(priceData.high_52w)}` },
                { label: "52週低點", value: `$${fmtNum(priceData.low_52w)}` },
              ].map(({ label, value }) => (
                <div
                  key={label}
                  className="bg-slate-800 border border-slate-700 rounded-xl p-4"
                >
                  <p className="text-xs text-slate-500 mb-1">{label}</p>
                  <p className="text-sm font-semibold text-slate-100">
                    {value}
                  </p>
                </div>
              ))}
            </div>
          )}

          {activeTab === "technical" && technicalData && (
            <div className="space-y-4">
              {/* RSI */}
              {technicalData.rsi != null && (
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-2">
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
                      className={`h-full rounded-full transition-all ${
                        technicalData.rsi > 70
                          ? "bg-red-400"
                          : technicalData.rsi < 30
                            ? "bg-green-400"
                            : "bg-indigo-400"
                      }`}
                      style={{ width: `${Math.min(technicalData.rsi, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-slate-600 mt-1">
                    <span>超賣 &lt;30</span>
                    <span>超買 &gt;70</span>
                  </div>
                </div>
              )}

              {/* MACD */}
              {technicalData.macd && (
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
                  <p className="text-sm text-slate-400 mb-3">MACD</p>
                  <div className="grid grid-cols-3 gap-3">
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
                          className={`text-sm font-semibold mt-0.5 ${color ?? "text-slate-100"}`}
                        >
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Moving Averages */}
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p className="text-sm text-slate-400 mb-3">移動平均線</p>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "SMA 20", value: technicalData.sma_20 },
                    { label: "SMA 50", value: technicalData.sma_50 },
                    { label: "SMA 200", value: technicalData.sma_200 },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-xs text-slate-500">{label}</p>
                      <p
                        className={`text-sm font-semibold mt-0.5 ${
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
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 h-40">
                  <p className="text-xs text-slate-500 mb-2">RSI 視覺化</p>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={[{ name: "RSI", value: technicalData.rsi }]}
                    >
                      <ReferenceLine
                        y={70}
                        stroke="#f87171"
                        strokeDasharray="3 3"
                      />
                      <ReferenceLine
                        y={30}
                        stroke="#4ade80"
                        strokeDasharray="3 3"
                      />
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 10, fill: "#64748b" }}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: "#64748b" }}
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="#818cf8"
                        strokeWidth={2}
                        dot
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          {activeTab === "fundamental" && fundamentalData && (
            <div className="space-y-4">
              {fundamentalData.description && (
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
                  <p className="text-xs text-slate-500 mb-2">公司簡介</p>
                  <p className="text-sm text-slate-300 leading-relaxed line-clamp-4">
                    {fundamentalData.description}
                  </p>
                  {(fundamentalData.sector || fundamentalData.industry) && (
                    <div className="flex gap-2 mt-3">
                      {fundamentalData.sector && (
                        <span className="px-2 py-1 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs rounded-full">
                          {fundamentalData.sector}
                        </span>
                      )}
                      {fundamentalData.industry && (
                        <span className="px-2 py-1 bg-slate-700 text-slate-400 text-xs rounded-full">
                          {fundamentalData.industry}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
                  <div
                    key={label}
                    className="bg-slate-800 border border-slate-700 rounded-xl p-4"
                  >
                    <p className="text-xs text-slate-500 mb-1">{label}</p>
                    <p className="text-sm font-semibold text-slate-100">
                      {value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
