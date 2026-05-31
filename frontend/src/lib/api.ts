import { auth } from "./firebase";
import type {
  StockPrice,
  Technicals,
  Fundamentals,
  InstitutionalData,
  MarginData,
} from "@/types/stock";

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://navi-backend-58156810941.asia-east1.run.app";

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await user.getIdToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/**
 * Unified fetch wrapper: handles auth headers, base URL, and error unwrapping.
 * Pass pre-fetched `headers` to avoid redundant getIdToken() calls when
 * firing multiple parallel requests (e.g. Stock page parallel fetches).
 */
async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  headers?: Record<string, string>,
): Promise<T> {
  const h = headers ?? (await getAuthHeaders());
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers: h });
  if (!res.ok) throw new Error(await res.text());
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

// ─── Knowledge ──────────────────────────────────────────────────────────────

export async function searchKnowledge(query: string) {
  return apiFetch(`/api/knowledge/search?query=${encodeURIComponent(query)}`);
}

// ─── Stock ───────────────────────────────────────────────────────────────────

export async function getStockPrice(
  symbol: string,
  headers?: Record<string, string>,
): Promise<StockPrice> {
  return apiFetch<StockPrice>(
    `/api/stock/${encodeURIComponent(symbol)}`,
    {},
    headers,
  );
}

export async function getStockTechnicals(
  symbol: string,
  headers?: Record<string, string>,
): Promise<Technicals> {
  return apiFetch<Technicals>(
    `/api/stock/${encodeURIComponent(symbol)}/technical`,
    {},
    headers,
  );
}

export async function getStockFundamentals(
  symbol: string,
  headers?: Record<string, string>,
): Promise<Fundamentals> {
  return apiFetch<Fundamentals>(
    `/api/stock/${encodeURIComponent(symbol)}/fundamental`,
    {},
    headers,
  );
}

export async function getStockInstitutional(
  symbol: string,
  headers?: Record<string, string>,
): Promise<InstitutionalData> {
  return apiFetch<InstitutionalData>(
    `/api/stock/${encodeURIComponent(symbol)}/institutional`,
    {},
    headers,
  );
}

export async function getStockMargin(
  symbol: string,
  headers?: Record<string, string>,
): Promise<MarginData> {
  return apiFetch<MarginData>(
    `/api/stock/${encodeURIComponent(symbol)}/margin`,
    {},
    headers,
  );
}

export interface StockSuggestion {
  code: string;
  name: string;
  ticker: string;
  market: string;
}

export async function searchStocks(q: string): Promise<StockSuggestion[]> {
  try {
    return await apiFetch<StockSuggestion[]>(
      `/api/stock/search?q=${encodeURIComponent(q)}`,
    );
  } catch {
    return [];
  }
}

// ─── Conversations ───────────────────────────────────────────────────────────

export interface Conversation {
  conversation_id: string;
  title: string;
  created_at: string;
  message_count: number;
}

export async function getConversations(): Promise<{
  conversations: Conversation[];
}> {
  return apiFetch<{ conversations: Conversation[] }>(`/api/chat/conversations`);
}

export interface StoredMessage {
  role: string;
  content: string;
  thinking?: ThinkingStep[];
  citations?: Citation[];
}

export async function getConversationMessages(
  conversationId: string,
): Promise<{ messages: StoredMessage[] }> {
  return apiFetch(
    `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
  );
}

export async function deleteConversation(conversationId: string) {
  return apiFetch(
    `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
}

// ─── Chat (SSE Streaming) ────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type ThinkingStep =
  | {
      type: "intent";
      intent: string;
      ticker?: string | null;
      confidence: number;
    }
  | { type: "tool_start"; tool: string; input?: Record<string, unknown> }
  | { type: "tool_end"; tool: string };

export interface Citation {
  id: number;
  type: string;
  source: string;
  title?: string | null;
  url?: string | null;
  detail?: string | null;
  note?: string | null;
  fetched_at?: string;
}

export interface QuotaErrorPayload {
  code: "QUOTA_EXCEEDED" | "ACCOUNT_SUSPENDED";
  message: string;
  tier: string;
  daily_limit: number;
  used_today: number;
  remaining: number;
  reset_at: string;
}

export interface ChatStreamOptions {
  message: string;
  conversationId?: string;
  onChunk: (text: string) => void;
  onThinkingStep: (step: ThinkingStep) => void;
  onCitations?: (citations: Citation[]) => void;
  onDone: (conversationId: string) => void;
  onError: (error: string) => void;
  onQuotaHeaders?: (headers: Headers) => void;
  onQuotaExceeded?: (payload: QuotaErrorPayload) => void;
}

export async function streamChat(options: ChatStreamOptions): Promise<void> {
  const {
    message,
    conversationId,
    onChunk,
    onThinkingStep,
    onCitations,
    onDone,
    onError,
    onQuotaHeaders,
    onQuotaExceeded,
  } = options;

  const user = auth.currentUser;
  if (!user) {
    onError("Not authenticated");
    return;
  }
  const token = await user.getIdToken();

  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
  });

  if (res.status === 429 && onQuotaExceeded) {
    try {
      const body = await res.json();
      const detail = body?.detail ?? body;
      if (detail && typeof detail === "object" && detail.code) {
        onQuotaExceeded(detail as QuotaErrorPayload);
        return;
      }
    } catch {
      // fall through to generic error
    }
  }

  if (!res.ok) {
    onError(`HTTP ${res.status}: ${await res.text()}`);
    return;
  }

  if (onQuotaHeaders) {
    onQuotaHeaders(res.headers);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    onError("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let capturedConvId = conversationId ?? ""; // will be set from first SSE event

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();

        // Backend sends literal "[DONE]" to signal end of stream
        if (data === "[DONE]") {
          onDone(capturedConvId);
          continue;
        }

        try {
          const parsed = JSON.parse(data);

          // First event: {"conversation_id": "xxx"}
          if (
            parsed.conversation_id &&
            !parsed.text &&
            !parsed.error &&
            !parsed.type
          ) {
            capturedConvId = parsed.conversation_id;
            continue;
          }

          // Thinking events: {"type": "intent" | "tool_start" | "tool_end", ...}
          if (
            parsed.type === "intent" ||
            parsed.type === "tool_start" ||
            parsed.type === "tool_end"
          ) {
            onThinkingStep(parsed as ThinkingStep);
            continue;
          }

          // Citations event: {"type": "citations", "citations": [...]}
          if (parsed.type === "citations" && Array.isArray(parsed.citations)) {
            onCitations?.(parsed.citations as Citation[]);
            continue;
          }

          // Content chunk: {"text": "..."}
          if (parsed.text) {
            onChunk(parsed.text);
            continue;
          }

          // Error event: {"error": "..."}
          if (parsed.error) {
            onError(parsed.error);
            continue;
          }
        } catch {
          // skip malformed lines
        }
      }
    }
  }
}

// ─── Portfolio ────────────────────────────────────────────────────────────────

export interface HoldingData {
  id: string;
  ticker: string;
  name: string;
  shares: number;
  avg_cost: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface HoldingWithPrice extends HoldingData {
  current_price: number | null;
  market_value: number;
  cost_basis: number;
  pnl: number;
  pnl_percent: number;
  currency: string;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_percent: number;
  holdings_count: number;
  holdings: HoldingWithPrice[];
}

export async function getPortfolio(): Promise<PortfolioSummary> {
  return apiFetch(`/api/portfolio`);
}

export async function getPortfolioHoldings(): Promise<HoldingData[]> {
  return apiFetch(`/api/portfolio/holdings`);
}

// ─── Quota ───────────────────────────────────────────────────────────────────

export interface QuotaStatus {
  tier: string;
  status: string;
  daily_limit: number;
  used_today: number;
  remaining: number;
  reset_at: string;
}

export async function getQuotaStatus(): Promise<QuotaStatus> {
  return apiFetch<QuotaStatus>(`/api/chat/quota`);
}

export interface FeatureAccessConfig {
  feature_key: string;
  display_name: string;
  description: string;
  allowed_tiers: string[];
  enabled: boolean;
  updated_at?: string;
  updated_by?: string;
}

export interface FeatureAccessItem extends FeatureAccessConfig {
  allowed: boolean;
  reason: string | null;
}

export interface FeatureAccessResponse {
  tier: string;
  status: string;
  features: FeatureAccessItem[];
}

export async function getFeatureAccess(): Promise<FeatureAccessResponse> {
  return apiFetch<FeatureAccessResponse>(`/api/features/access`);
}

// ─── Admin ───────────────────────────────────────────────────────────────────

export interface AdminUser {
  uid: string;
  email: string;
  display_name: string;
  tier: string;
  status: string;
  custom_daily_limit: number | null;
  notes: string;
  created_at?: string;
  updated_at?: string;
  last_active_at?: string;
}

export interface QuotaConfig {
  tier: string;
  daily_limit: number;
  per_minute_limit: number;
  description?: string;
}

export interface UsageDay {
  date: string;
  chat_count: number;
}

export interface AdminUsageSummary {
  days: number;
  total_messages: number;
  active_users: number;
  daily_breakdown: { date: string; count: number }[];
  top_users: { uid: string; count: number }[];
}

export interface UsageLog {
  id: string;
  uid: string;
  email: string;
  tier: string;
  endpoint: string;
  conversation_id: string | null;
  question_preview: string;
  blocked: boolean;
  block_reason: string | null;
  timestamp: string;
}

export async function adminCheckMe(): Promise<{ admin: boolean; uid: string }> {
  return apiFetch(`/api/admin/me`);
}

export async function adminListUsers(
  params: {
    q?: string;
    tier?: string;
    status?: string;
    limit?: number;
  } = {},
): Promise<{ users: AdminUser[] }> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.tier) qs.set("tier", params.tier);
  if (params.status) qs.set("status", params.status);
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch(`/api/admin/users${suffix}`);
}

export async function adminGetUser(
  uid: string,
): Promise<{ user: AdminUser; usage: UsageDay[] }> {
  return apiFetch(`/api/admin/users/${encodeURIComponent(uid)}`);
}

export async function adminUpdateUser(
  uid: string,
  patch: {
    tier?: string;
    status?: string;
    custom_daily_limit?: number | null;
    notes?: string;
  },
): Promise<{ user: AdminUser }> {
  return apiFetch(`/api/admin/users/${encodeURIComponent(uid)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function adminListQuotaConfigs(): Promise<{
  configs: QuotaConfig[];
}> {
  return apiFetch(`/api/admin/quota-configs`);
}

export async function adminUpdateQuotaConfig(
  tier: string,
  patch: Partial<QuotaConfig>,
): Promise<{ config: QuotaConfig }> {
  return apiFetch(`/api/admin/quota-configs/${encodeURIComponent(tier)}`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function adminListFeatureAccessConfigs(): Promise<{
  configs: FeatureAccessConfig[];
}> {
  return apiFetch(`/api/admin/feature-access-configs`);
}

export async function adminUpdateFeatureAccessConfig(
  featureKey: string,
  patch: Partial<
    Pick<FeatureAccessConfig, "enabled" | "allowed_tiers" | "description">
  >,
): Promise<{ config: FeatureAccessConfig }> {
  return apiFetch(
    `/api/admin/feature-access-configs/${encodeURIComponent(featureKey)}`,
    {
      method: "PUT",
      body: JSON.stringify(patch),
    },
  );
}

export async function adminGetUsageSummary(
  days = 30,
): Promise<AdminUsageSummary> {
  return apiFetch(`/api/admin/usage/summary?days=${days}`);
}

export async function adminListLogs(
  params: {
    uid?: string;
    blocked?: boolean;
    limit?: number;
  } = {},
): Promise<{ logs: UsageLog[] }> {
  const qs = new URLSearchParams();
  if (params.uid) qs.set("uid", params.uid);
  if (params.blocked !== undefined) qs.set("blocked", String(params.blocked));
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch(`/api/admin/logs${suffix}`);
}

export async function addHolding(data: {
  ticker: string;
  shares: number;
  avg_cost: number;
  name?: string;
  notes?: string;
}): Promise<HoldingData> {
  return apiFetch(`/api/portfolio/holdings`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateHolding(
  holdingId: string,
  data: { shares?: number; avg_cost?: number; notes?: string },
): Promise<HoldingData> {
  return apiFetch(`/api/portfolio/holdings/${encodeURIComponent(holdingId)}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteHolding(holdingId: string): Promise<void> {
  await apiFetch(`/api/portfolio/holdings/${encodeURIComponent(holdingId)}`, {
    method: "DELETE",
  });
}

// ─── Backtest ─────────────────────────────────────────────────────────────────

export interface BacktestTrade {
  date: string;
  action: "buy" | "sell";
  price: number;
  shares: number;
  value: number;
  reason: string;
}

export interface EquityPoint {
  date: string;
  equity: number;
  drawdown: number;
}

export interface BacktestResult {
  ticker: string;
  strategy: string;
  period: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_equity: number;
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_win: number;
  avg_loss: number;
  benchmark_return: number;
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
  error: string;
}

export interface BacktestRequest {
  ticker: string;
  strategy: string;
  period: string;
  initial_capital: number;
}

export interface StrategyInfo {
  name: string;
  label: string;
  description: string;
  params: Record<
    string,
    { type: string; default: number | string; description: string }
  >;
}

export async function runBacktest(
  req: BacktestRequest,
): Promise<BacktestResult> {
  return apiFetch(`/api/backtest`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getStrategies(): Promise<{ strategies: StrategyInfo[] }> {
  return apiFetch(`/api/backtest/strategies`);
}
