// Centralized type definitions for stock-related data

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
  history?: Array<{ date: string; close: number }>;
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
  summary: string;
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

export type Tab = "overview" | "technical" | "fundamental" | "institutional";
