// Screener report types — mirror backend models in api/routes/screener.py

export type ScreenerProfile = "value" | "momentum";
export type ScreenerFrequency = "daily" | "weekly";

export interface ReportSummary {
  report_id: string;
  profile: ScreenerProfile;
  frequency: ScreenerFrequency;
  final_count: number;
  industries_covered: string[];
  duration_seconds?: number | null;
  status?: string;
  generated_at?: { _seconds?: number; seconds?: number } | string | null;
}

export interface PickSnapshot {
  price?: number | null;
  pe?: number | null;
  pb?: number | null;
  roe?: number | null;
  dividend_yield?: number | null;
  revenue_growth?: number | null;
  profit_margin?: number | null;
  return_3m?: number | null;
  return_6m?: number | null;
  rel_strength_3m?: number | null;
  volume_expansion?: number | null;
}

export interface PickTargetPrice {
  low: number;
  mid: number;
  high: number;
}

export interface PickDoc {
  ticker: string;
  name: string;
  industry: string;
  rank_in_industry: number;
  factor_scores: Record<string, number>;
  snapshot: PickSnapshot;
  thesis: string;
  kb_citations: string[];
  target_price: PickTargetPrice;
  upside_pct: number;
  stop_loss: number;
  risk_reward_ratio: number;
  risks: string[];
  confidence: number;
}

export interface ReportDetail {
  report: ReportSummary;
  picks_by_industry: Record<string, PickDoc[]>;
}

export interface EmailSubscription {
  user_id: string;
  email: string;
  enabled: boolean;
  profiles: ScreenerProfile[];
  frequencies: ScreenerFrequency[];
  updated_at?: string | null;
}
