// Centralized type definitions for stock-related data

export interface PricePoint {
  date: string;
  close: number;
}

/** 走勢圖可選期間；與後端 `_PERIOD_SPEC` 的 key 對應。 */
export const CHART_PERIODS = ["1mo", "3mo", "6mo", "1y", "5y", "10y", "max"] as const;
export type ChartPeriod = (typeof CHART_PERIODS)[number];

export const CHART_PERIOD_LABELS: Record<ChartPeriod, string> = {
  "1mo": "1個月",
  "3mo": "3個月",
  "6mo": "6個月",
  "1y": "1年",
  "5y": "5年",
  "10y": "10年",
  max: "全部",
};

/** 後端長期間會降頻，標示實際 K 棒週期避免誤讀。 */
export const INTERVAL_LABELS: Record<string, string> = {
  "1d": "日線",
  "1wk": "週線",
  "1mo": "月線",
};

export interface StockPrice {
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
  as_of_date: string;
  data_source: string;
  is_intraday: boolean;
}

export interface Technicals {
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
  /** 依 period 截取的收盤價序列（由舊到新）；抓取失敗時為空陣列。 */
  history: PricePoint[];
  /** history 的實際 K 棒週期："1d" / "1wk" / "1mo"。 */
  history_interval: string;
  summary: string;
}

export interface PopularStockItem {
  ticker: string;
  code: string;
  name: string;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  volume_shares: number | null;
  /** 成交值（元） */
  turnover: number | null;
  /** 近一個月收盤序列（由舊到新），供 sparkline 使用 */
  spark: number[];
}

export interface PopularBoard {
  key: string;
  label: string;
  items: PopularStockItem[];
}

export interface PopularData {
  boards: PopularBoard[];
  as_of_date: string;
  note: string;
}

export interface InstitutionalDaily {
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

export interface InstitutionalData {
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

export interface MarginDailyData {
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

export interface MarginData {
  ticker: string;
  name: string;
  records: MarginDailyData[];
  latest: MarginDailyData | null;
  margin_change: number;
  short_change: number;
  error: string;
}

export interface Fundamentals {
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

export interface NewsArticle {
  title: string;
  link: string;
  source: string;
  published: string;
}

export interface NewsData {
  ticker: string;
  query: string;
  articles: NewsArticle[];
  error: string;
}

export interface MonthlyRevenueData {
  ticker: string;
  label: string;
  revenue: number | null;
  yoy: number | null;
  mom: number | null;
  yoy_acc: number | null;
}

export interface IndustryPeData {
  ticker: string;
  stock_pe: number;
  industry: string;
  percentile: number;
  sample_size: number;
  median_pe: number;
}

export type Tab = "overview" | "technical" | "fundamental" | "institutional" | "news";
