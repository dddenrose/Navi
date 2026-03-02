import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { streamChat, getConversations, deleteConversation } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

interface Conversation {
  conversation_id: string;
  created_at: string;
  message_count: number;
}

export default function Chat() {
  const { conversationId: paramConvId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [currentConvId, setCurrentConvId] = useState<string | undefined>(
    paramConvId,
  );
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [sidebarLoading, setSidebarLoading] = useState(true);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load conversations list
  const loadConversations = useCallback(async () => {
    try {
      setSidebarLoading(true);
      const data = await getConversations();
      setConversations(data.conversations ?? []);
    } catch {
      // silently fail
    } finally {
      setSidebarLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Handle initial message from Dashboard quick questions
  useEffect(() => {
    const initialMessage = (location.state as { initialMessage?: string })
      ?.initialMessage;
    if (initialMessage) {
      setInput(initialMessage);
      textareaRef.current?.focus();
      // Clear location state
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.state, location.pathname, navigate]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || streaming) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", streaming: true },
    ]);
    setStreaming(true);

    let fullContent = "";

    await streamChat({
      message: trimmed,
      conversationId: currentConvId,
      onChunk: (chunk) => {
        fullContent += chunk;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: fullContent,
              streaming: true,
            };
          }
          return updated;
        });
      },
      onDone: (convId) => {
        setCurrentConvId(convId);
        navigate(`/chat/${convId}`, { replace: true });
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = { ...last, streaming: false };
          }
          return updated;
        });
        setStreaming(false);
        loadConversations();
      },
      onError: (err) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: `錯誤：${err}`,
              streaming: false,
            };
          }
          return updated;
        });
        setStreaming(false);
      },
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setCurrentConvId(undefined);
    navigate("/chat");
  };

  const handleDeleteConversation = async (
    convId: string,
    e: React.MouseEvent,
  ) => {
    e.stopPropagation();
    try {
      await deleteConversation(convId);
      setConversations((prev) =>
        prev.filter((c) => c.conversation_id !== convId),
      );
      if (currentConvId === convId) {
        startNewChat();
      }
    } catch {
      // silently fail
    }
  };

  return (
    <div className="flex h-screen">
      {/* Conversation sidebar */}
      <div className="w-56 bg-slate-800/50 border-r border-slate-700 flex flex-col">
        <div className="p-3 border-b border-slate-700">
          <button
            onClick={startNewChat}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2 text-sm font-medium transition-colors"
          >
            <span>＋</span> 新對話
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sidebarLoading ? (
            <p className="text-xs text-slate-500 px-2 py-3">載入中...</p>
          ) : conversations.length === 0 ? (
            <p className="text-xs text-slate-500 px-2 py-3">尚無對話記錄</p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.conversation_id}
                onClick={() => {
                  setCurrentConvId(conv.conversation_id);
                  navigate(`/chat/${conv.conversation_id}`);
                  setMessages([]);
                }}
                className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-colors ${
                  currentConvId === conv.conversation_id
                    ? "bg-slate-700 text-slate-200"
                    : ""
                }`}
              >
                <span className="truncate">對話 · {conv.message_count} 則</span>
                <button
                  onClick={(e) =>
                    handleDeleteConversation(conv.conversation_id, e)
                  }
                  className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-opacity ml-1 flex-shrink-0"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="text-4xl mb-4">🧭</div>
              <h2 className="text-xl font-semibold text-white mb-2">
                Navi 助理
              </h2>
              <p className="text-slate-400 text-sm max-w-sm">
                您好！我可以幫您分析股票、解釋技術指標，以及回答投資相關問題。
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-2xl px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-sm"
                    : "bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-sm"
                }`}
              >
                {msg.content}
                {msg.streaming && (
                  <span className="inline-block w-1.5 h-4 bg-indigo-400 animate-pulse ml-0.5 align-middle" />
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-slate-700 p-4">
          <div className="flex gap-3 max-w-3xl mx-auto">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="輸入您的問題... (Enter 發送，Shift+Enter 換行)"
              disabled={streaming}
              rows={1}
              className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none transition-colors disabled:opacity-50"
              style={{ minHeight: "48px", maxHeight: "120px" }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl px-4 py-3 text-sm font-medium transition-colors flex-shrink-0"
            >
              {streaming ? "..." : "發送"}
            </button>
          </div>
          <p className="text-xs text-slate-600 text-center mt-2">
            Navi 可能會犯錯，請自行驗證重要投資決策
          </p>
        </div>
      </div>
    </div>
  );
}
