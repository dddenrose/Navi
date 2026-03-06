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
  title: string;
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
  const [chatSidebarOpen, setChatSidebarOpen] = useState(true);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // rerender-use-ref-transient-values: accumulate streaming content in ref, flush via rAF
  const streamContentRef = useRef("");
  const rafRef = useRef<number | null>(null);

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
        streamContentRef.current = fullContent;
        if (rafRef.current == null) {
          rafRef.current = requestAnimationFrame(() => {
            rafRef.current = null;
            const content = streamContentRef.current;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content,
                  streaming: true,
                };
              }
              return updated;
            });
          });
        }
      },
      onDone: (convId) => {
        // Flush any pending rAF
        if (rafRef.current != null) {
          cancelAnimationFrame(rafRef.current);
          rafRef.current = null;
        }
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
    <div className="flex h-[calc(100vh-3.5rem)] md:h-screen">
      {/* Sidebar toggle button (mobile: fixed bottom-left, desktop: top of chat area) */}
      <button
        onClick={() => setChatSidebarOpen(!chatSidebarOpen)}
        className="fixed bottom-24 left-4 z-30 md:hidden w-10 h-10 rounded-full flex items-center justify-center text-white shadow-lg"
        style={{
          background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
          boxShadow: "0 4px 16px rgba(99,102,241,0.4)",
        }}
        aria-label="切換對話列表"
      >
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-4 h-4"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M2 4.75A.75.75 0 012.75 4h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 4.75zM2 10a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 10zm0 5.25a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75a.75.75 0 01-.75-.75z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {/* Conversation history sidebar */}
      <div
        className={`flex-col flex-shrink-0 transition-all duration-200 ease-out ${
          chatSidebarOpen
            ? "w-60 flex"
            : "w-0 overflow-hidden hidden md:flex md:w-0"
        }`}
        style={{
          background: "var(--sidebar-bg)",
          borderRight: chatSidebarOpen ? "1px solid var(--border)" : "none",
        }}
      >
        <div
          className="p-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <button
            onClick={startNewChat}
            className="w-full flex items-center justify-center gap-2 rounded-xl py-3 text-xs font-medium text-white transition-opacity hover:opacity-90"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
          >
            <svg
              viewBox="0 0 16 16"
              fill="currentColor"
              className="w-3.5 h-3.5"
              aria-hidden="true"
            >
              <path d="M8 2a.5.5 0 01.5.5v5h5a.5.5 0 010 1h-5v5a.5.5 0 01-1 0v-5h-5a.5.5 0 010-1h5v-5A.5.5 0 018 2z" />
            </svg>
            新對話
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {sidebarLoading ? (
            <p className="text-xs text-slate-700 px-3 py-4 text-center">
              載入中…
            </p>
          ) : conversations.length === 0 ? (
            <p className="text-xs text-slate-700 px-3 py-4 text-center">
              尚無對話記錄
            </p>
          ) : (
            conversations.map((conv) => (
              <button
                type="button"
                key={conv.conversation_id}
                onClick={() => {
                  setCurrentConvId(conv.conversation_id);
                  navigate(`/chat/${conv.conversation_id}`);
                  setMessages([]);
                }}
                className="group w-full flex items-center justify-between px-3 py-3.5 rounded-xl cursor-pointer transition-colors text-left"
                style={
                  currentConvId === conv.conversation_id
                    ? {
                        background: "rgba(99,102,241,0.12)",
                        border: "1px solid rgba(99,102,241,0.2)",
                      }
                    : { border: "1px solid transparent" }
                }
              >
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-xs truncate leading-relaxed ${
                      currentConvId === conv.conversation_id
                        ? "text-slate-300"
                        : "text-slate-600 group-hover:text-slate-400"
                    }`}
                  >
                    {conv.title || "對話記錄"}
                  </p>
                  <p className="text-xs text-slate-700 mt-0.5">
                    {conv.message_count} 則訊息
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) =>
                    handleDeleteConversation(conv.conversation_id, e)
                  }
                  aria-label="刪除對話"
                  className="opacity-0 group-hover:opacity-100 text-slate-700 hover:text-red-400 transition-opacity ml-1 flex-shrink-0 text-xs"
                >
                  ✕
                </button>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Desktop sidebar toggle */}
        <div
          className="hidden md:flex items-center h-12 px-4 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <button
            onClick={() => setChatSidebarOpen(!chatSidebarOpen)}
            className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-500 hover:text-slate-200 rounded-lg transition-colors hover:bg-white/5"
            aria-label={chatSidebarOpen ? "隱藏對話記錄" : "顯示對話記錄"}
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-4 h-4 transition-transform duration-200 ${chatSidebarOpen ? "" : "rotate-180"}`}
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h6a1 1 0 110 2H4a1 1 0 01-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {chatSidebarOpen ? "隱藏記錄" : "對話記錄"}
          </button>
        </div>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 md:py-8">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center animate-fade-in">
              <div
                className="w-20 h-20 rounded-2xl flex items-center justify-center text-4xl mb-7"
                style={{
                  background:
                    "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.12))",
                  border: "1px solid rgba(99,102,241,0.2)",
                }}
              >
                🧭
              </div>
              <h2
                className="text-xl font-semibold text-slate-200 mb-3"
                style={{ textWrap: "balance" }}
              >
                Navi 投資助理
              </h2>
              <p className="text-slate-500 text-sm max-w-xs leading-loose">
                您好！我可以幫您分析股票、解釋技術指標，以及回答投資相關問題。
              </p>
            </div>
          ) : null}
          <div className="max-w-3xl mx-auto space-y-6" aria-live="polite">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-4 animate-fade-up ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                style={{ animationDelay: "0ms" }}
              >
                {msg.role === "assistant" && (
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-sm flex-shrink-0 mt-0.5"
                    aria-hidden="true"
                    style={{
                      background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                    }}
                  >
                    🧭
                  </div>
                )}
                <div
                  className={`max-w-2xl px-5 py-4 rounded-2xl text-sm leading-8 whitespace-pre-wrap break-words ${
                    msg.role === "user" ? "rounded-tr-sm" : "rounded-tl-sm"
                  }`}
                  style={
                    msg.role === "user"
                      ? {
                          background:
                            "linear-gradient(135deg, #6366f1, #7c3aed)",
                          color: "white",
                        }
                      : {
                          background: "var(--overlay-bg)",
                          border: "1px solid var(--border)",
                          color: "var(--text-link)",
                        }
                  }
                >
                  {msg.content}
                  {msg.streaming && (
                    <span className="cursor-blink inline-block w-0.5 h-4 bg-indigo-400 ml-0.5 align-text-bottom" />
                  )}
                </div>
              </div>
            ))}
          </div>
          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div
          className="px-4 py-4 md:px-8 md:py-5"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <div
            className="flex gap-3 max-w-3xl mx-auto items-end rounded-2xl px-5 py-4 transition-[border-color,box-shadow]"
            style={{
              background: "var(--overlay-bg)",
              border: `1px solid ${streaming ? "rgba(99,102,241,0.3)" : "var(--border)"}`,
              boxShadow: streaming ? "0 0 0 3px rgba(99,102,241,0.1)" : "none",
            }}
          >
            <label htmlFor="chat-input" className="sr-only">
              輸入問題
            </label>
            <textarea
              id="chat-input"
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="輸入問題… (Enter 發送，Shift+Enter 換行)"
              disabled={streaming}
              rows={1}
              className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-700 resize-none focus:outline-none focus-visible:outline-none disabled:opacity-40"
              style={{ minHeight: "24px", maxHeight: "120px" }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              aria-label="發送訊息"
              className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-opacity disabled:opacity-30 disabled:cursor-not-allowed"
              style={{
                background:
                  !input.trim() || streaming
                    ? "var(--overlay-subtle)"
                    : "linear-gradient(135deg, #6366f1, #8b5cf6)",
                boxShadow:
                  !input.trim() || streaming
                    ? "none"
                    : "0 2px 12px rgba(99,102,241,0.4)",
              }}
            >
              {streaming ? (
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="w-3.5 h-3.5 text-slate-500"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-11.25a.75.75 0 00-1.5 0v4.59L7.3 9.24a.75.75 0 00-1.1 1.02l3.25 3.5a.75.75 0 001.1 0l3.25-3.5a.75.75 0 10-1.1-1.02l-1.95 2.1V6.75z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : (
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="w-3.5 h-3.5 text-white"
                  aria-hidden="true"
                >
                  <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                </svg>
              )}
            </button>
          </div>
          <p className="text-xs text-slate-700 text-center mt-2.5">
            Navi 可能會犯錯，重要投資決策請自行驗證
          </p>
        </div>
      </div>
    </div>
  );
}
