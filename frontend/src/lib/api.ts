import { auth } from "./firebase";

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://navi-backend-58156810941.asia-east1.run.app";

async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await user.getIdToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/**
 * Pre-fetch headers once, then pass to multiple API calls
 * to avoid redundant getIdToken() round-trips.
 */
export { getAuthHeaders };

// ─── Knowledge ──────────────────────────────────────────────────────────────

export async function searchKnowledge(query: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${BASE_URL}/api/knowledge/search?query=${encodeURIComponent(query)}`,
    {
      headers,
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Stock ───────────────────────────────────────────────────────────────────

export async function getStockPrice(
  symbol: string,
  headers?: Record<string, string>,
) {
  const h = headers ?? (await getAuthHeaders());
  const res = await fetch(`${BASE_URL}/api/stock/${symbol}`, {
    headers: h,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStockTechnicals(
  symbol: string,
  headers?: Record<string, string>,
) {
  const h = headers ?? (await getAuthHeaders());
  const res = await fetch(`${BASE_URL}/api/stock/${symbol}/technical`, {
    headers: h,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStockFundamentals(
  symbol: string,
  headers?: Record<string, string>,
) {
  const h = headers ?? (await getAuthHeaders());
  const res = await fetch(`${BASE_URL}/api/stock/${symbol}/fundamental`, {
    headers: h,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Conversations ───────────────────────────────────────────────────────────

export async function getConversations() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/chat/conversations`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteConversation(conversationId: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(
    `${BASE_URL}/api/chat/conversations/${conversationId}`,
    {
      method: "DELETE",
      headers,
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Chat (SSE Streaming) ────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatStreamOptions {
  message: string;
  conversationId?: string;
  onChunk: (text: string) => void;
  onDone: (conversationId: string) => void;
  onError: (error: string) => void;
}

export async function streamChat(options: ChatStreamOptions): Promise<void> {
  const { message, conversationId, onChunk, onDone, onError } = options;

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

  if (!res.ok) {
    onError(`HTTP ${res.status}: ${await res.text()}`);
    return;
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
          if (parsed.conversation_id && !parsed.text && !parsed.error) {
            capturedConvId = parsed.conversation_id;
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
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/portfolio`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getPortfolioHoldings(): Promise<HoldingData[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/portfolio/holdings`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function addHolding(data: {
  ticker: string;
  shares: number;
  avg_cost: number;
  name?: string;
  notes?: string;
}): Promise<HoldingData> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/portfolio/holdings`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateHolding(
  holdingId: string,
  data: { shares?: number; avg_cost?: number; notes?: string },
): Promise<HoldingData> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/portfolio/holdings/${holdingId}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteHolding(holdingId: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/portfolio/holdings/${holdingId}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error(await res.text());
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
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/backtest`, {
    method: "POST",
    headers,
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStrategies(): Promise<{ strategies: StrategyInfo[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/backtest/strategies`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
