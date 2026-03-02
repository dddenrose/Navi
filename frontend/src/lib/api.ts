import { auth } from "./firebase";

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://navi-backend-wankxbiojq-de.a.run.app";

async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await user.getIdToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

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

export async function getStockPrice(symbol: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/stock/price/${symbol}`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStockTechnicals(symbol: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/stock/technical/${symbol}`, {
    headers,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStockFundamentals(symbol: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}/api/stock/fundamental/${symbol}`, {
    headers,
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
