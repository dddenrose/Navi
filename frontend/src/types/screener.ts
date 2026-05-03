// Screener report types — mirror backend models in api/routes/screener.py
// 新版 (rule-based + LLM-as-interpreter) schema

export type ScreenerProfile = "value" | "momentum";
export type ScreenerFrequency = "daily" | "weekly";
export type FinalGrade = "Strong Pick" | "Pick" | "Watch" | "Reject" | string;
export type Verdict = "qualified" | "rejected" | string;
export type RuleSeverity = "critical" | "warning" | "info" | string;
export type ValueTrapCheck = "no_concern" | "watch" | "concern" | string;

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
  market_cap?: number | null;
  dividend_yield?: number | null;
  roe_3y_avg?: number | null;
  revenue_cagr_3y?: number | null;
  revenue_yoy_latest?: number | null;
  fcf_positive_years?: number | null;
  eps_positive_quarters?: number | null;
  debt_ratio?: number | null;
  current_ratio?: number | null;
  gross_margin_std_4q?: number | null;
  eps_ttm?: number | null;
  return_3m?: number | null;
  return_6m?: number | null;
  rel_strength_6m?: number | null;
  sma_60?: number | null;
  sma_120?: number | null;
  volume_ratio_5_20?: number | null;
  rsi_14?: number | null;
  high_60d?: number | null;
  foreign_net_5d?: number | null;
  foreign_net_20d?: number | null;
  foreign_consecutive_days?: number | null;
  industry_pe_median?: number | null;
  industry_pb_median?: number | null;
  industry_size?: number | null;
}

export interface RuleCheck {
  rule_id: string;
  name: string;
  rule: string;
  actual: string | number | null;
  reference: string | number | null;
  passed: boolean;
  severity: RuleSeverity;
}

export interface ScoringTrace {
  verdict: Verdict;
  final_grade: FinalGrade;
  rejection_reason?: string;
  missing_data_count?: number;
  missing_data_rule_ids?: string[];
  stage1_checks: RuleCheck[];
  must_pass: { passed: number; total: number; checks: RuleCheck[] };
  bonus: { passed: number; required: number; checks: RuleCheck[] };
  disqualifier: { triggered: string[]; checks: RuleCheck[] };
}

export interface Valuation {
  method?: string;
  fair_value_low?: number | null;
  fair_value_mid?: number | null;
  fair_value_high?: number | null;
  buy_zone_upper?: number | null;
  implied_upside_mid_pct?: number | null;
  data_used?: Record<string, unknown>;
  notes?: string;
}

export interface Interpretation {
  narrative: string;
  key_context: string[];
  warnings: string[];
  value_trap_check: ValueTrapCheck;
  value_trap_reason: string;
}

export interface PickDoc {
  ticker: string;
  name: string;
  industry: string;
  rank_in_industry: number;
  industry_size: number;
  final_grade: FinalGrade;
  verdict: Verdict;
  snapshot: PickSnapshot;
  scoring_trace: ScoringTrace;
  valuation: Valuation;
  interpretation: Interpretation;
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
