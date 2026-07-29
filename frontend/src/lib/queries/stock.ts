import { useQuery } from "@tanstack/react-query";
import {
  getPopularStocks,
  getStockFundamentals,
  getStockIndustryPe,
  getStockInstitutional,
  getStockMargin,
  getStockMonthlyRevenue,
  getStockNews,
  getStockPrice,
  getStockTechnicals,
  searchStocks,
} from "@/lib/api";
import type { ChartPeriod } from "@/types/stock";

/**
 * 個股資料的 React Query 層。
 *
 * 為什麼要有這一層：個股頁一次要打 4–6 支 API，而使用者的實際操作是
 * 「查 A → 查 B → 切回 A」「在分頁之間來回切」。沒有快取時每一次來回都是
 * 完整重打，包含 Firebase 換 token、後端驗 token、查 Firestore 權限，
 * 最後才拿到後端本來就已經快取好的同一份資料。
 *
 * staleTime 一律對齊或短於後端 TTL（見各 hook 註解），所以快取命中時
 * 看到的資料不會比重打一次 API 更舊——重打只是拿回同一份後端快照。
 */

const MINUTE = 60_000;

/**
 * queryKey 規範：`["stock", <端點>, <ticker>, ...參數]`。
 * 前綴一致，之後要一次失效整個個股區塊只要
 * `queryClient.invalidateQueries({ queryKey: stockKeys.all })`。
 */
export const stockKeys = {
  all: ["stock"] as const,
  price: (symbol: string) => ["stock", "price", symbol] as const,
  technical: (symbol: string, period: ChartPeriod) =>
    ["stock", "technical", symbol, period] as const,
  fundamental: (symbol: string) => ["stock", "fundamental", symbol] as const,
  institutional: (symbol: string) =>
    ["stock", "institutional", symbol] as const,
  margin: (symbol: string) => ["stock", "margin", symbol] as const,
  news: (symbol: string, limit: number) =>
    ["stock", "news", symbol, limit] as const,
  monthlyRevenue: (symbol: string) =>
    ["stock", "monthly-revenue", symbol] as const,
  industryPe: (symbol: string) => ["stock", "industry-pe", symbol] as const,
  popular: (limit?: number) => ["stock", "popular", limit ?? null] as const,
  search: (query: string) => ["stock", "search", query] as const,
};

/** 台股才有籌碼與融資券資料；美股問了也只會拿到 404。 */
export function isTwseTicker(symbol: string): boolean {
  return symbol.endsWith(".TW") || symbol.endsWith(".TWO");
}

/** 報價。後端台股快照 TTL 30 分鐘、yfinance info 5 分鐘，前端訂 1 分鐘。 */
export function useStockPrice(symbol: string) {
  return useQuery({
    queryKey: stockKeys.price(symbol),
    queryFn: () => getStockPrice(symbol),
    enabled: Boolean(symbol),
    staleTime: MINUTE,
  });
}

/**
 * 技術指標與走勢圖序列。
 *
 * `placeholderData` 只在「同一檔股票、換期間」時沿用上一筆資料，
 * 讓期間切換不閃圖；換股票時回傳 undefined，避免把上一檔的走勢圖
 * 掛在新股票的標題底下。
 */
export function useStockTechnicals(symbol: string, period: ChartPeriod) {
  return useQuery({
    queryKey: stockKeys.technical(symbol, period),
    queryFn: () => getStockTechnicals(symbol, undefined, period),
    enabled: Boolean(symbol),
    staleTime: 5 * MINUTE,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[2] === symbol ? previous : undefined,
  });
}

/** 基本面。財報為季頻資料，30 分鐘內不需要重抓。 */
export function useStockFundamentals(symbol: string) {
  return useQuery({
    queryKey: stockKeys.fundamental(symbol),
    queryFn: () => getStockFundamentals(symbol),
    enabled: Boolean(symbol),
    staleTime: 30 * MINUTE,
  });
}

/** 三大法人買賣超（僅台股）。日頻資料，盤後才更新。 */
export function useStockInstitutional(symbol: string) {
  return useQuery({
    queryKey: stockKeys.institutional(symbol),
    queryFn: () => getStockInstitutional(symbol),
    enabled: Boolean(symbol) && isTwseTicker(symbol),
    staleTime: 30 * MINUTE,
  });
}

/** 融資融券（僅台股）。同上，日頻。 */
export function useStockMargin(symbol: string) {
  return useQuery({
    queryKey: stockKeys.margin(symbol),
    queryFn: () => getStockMargin(symbol),
    enabled: Boolean(symbol) && isTwseTicker(symbol),
    staleTime: 30 * MINUTE,
  });
}

/** 個股新聞。對齊後端 `_STOCK_NEWS_CACHE_TTL`（30 分鐘）。 */
export function useStockNews(symbol: string, limit = 10) {
  return useQuery({
    queryKey: stockKeys.news(symbol, limit),
    queryFn: () => getStockNews(symbol, limit),
    enabled: Boolean(symbol),
    staleTime: 30 * MINUTE,
  });
}

/** 月營收。後端 daily TTL（24 小時），前端訂 1 小時已遠比後端積極。 */
export function useStockMonthlyRevenue(symbol: string) {
  return useQuery({
    queryKey: stockKeys.monthlyRevenue(symbol),
    queryFn: () => getStockMonthlyRevenue(symbol),
    enabled: Boolean(symbol),
    staleTime: 60 * MINUTE,
  });
}

/** 產業 PE 分位數。後端同為 daily TTL。 */
export function useStockIndustryPe(symbol: string) {
  return useQuery({
    queryKey: stockKeys.industryPe(symbol),
    queryFn: () => getStockIndustryPe(symbol),
    enabled: Boolean(symbol),
    staleTime: 60 * MINUTE,
  });
}

/** 熱門標的。對齊後端 `_CACHE_TTL`（30 分鐘）。 */
export function usePopularStocks(enabled = true, limit?: number) {
  return useQuery({
    queryKey: stockKeys.popular(limit),
    queryFn: () => getPopularStocks(undefined, limit),
    enabled,
    staleTime: 30 * MINUTE,
  });
}

/**
 * 搜尋建議。上市櫃清單一天只變動一次，快取得久一點，
 * 使用者刪字回退到打過的前綴時就不會再打一次 API。
 * `searchStocks` 內部已吞掉錯誤回傳空陣列，所以這裡不需要 retry。
 */
export function useStockSearch(query: string) {
  return useQuery({
    queryKey: stockKeys.search(query),
    queryFn: () => searchStocks(query),
    enabled: query.length > 0,
    staleTime: 10 * MINUTE,
    retry: false,
  });
}
