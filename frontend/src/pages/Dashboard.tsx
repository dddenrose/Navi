import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

const quickStocks = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL"];

const quickQuestions = [
  "什麼是 RSI 指標？",
  "MACD 如何判斷買賣點？",
  "移動平均線的使用方式？",
  "如何計算本益比？",
];

export default function Dashboard() {
  const { user } = useAuthStore();
  const navigate = useNavigate();

  const greeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "早安";
    if (hour < 18) return "午安";
    return "晚安";
  };

  return (
    <div className="px-10 py-10 max-w-4xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="mb-14">
        <p className="text-sm text-slate-600 mb-1 tracking-widest uppercase">
          {new Date().toLocaleDateString("zh-TW", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1 className="text-2xl font-semibold text-slate-100">
          {greeting()}，
          <span className="gradient-text">{user?.displayName ?? "投資人"}</span>
        </h1>
        <p className="text-slate-500 text-sm mt-1.5">
          歡迎使用 Navi AI 投資分析助理
        </p>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-14">
        <button
          onClick={() => navigate("/chat")}
          className="group relative rounded-2xl p-7 text-left transition-all duration-200 overflow-hidden hover:scale-[1.02]"
          style={{
            background:
              "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.12))",
            border: "1px solid rgba(99,102,241,0.25)",
          }}
        >
          {/* Glow on hover */}
          <div
            className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
            style={{
              background:
                "radial-gradient(circle at 50% 50%, rgba(99,102,241,0.12), transparent 70%)",
            }}
          />
          <div className="relative">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center mb-5 text-lg"
              style={{ background: "rgba(99,102,241,0.25)" }}
            >
              💬
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">
              開始 AI 對話
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              向 AI 提問投資策略、技術指標、個股分析
            </p>
          </div>
          <div className="absolute bottom-5 right-5 text-indigo-400/50 group-hover:text-indigo-400 transition-colors text-xl">
            →
          </div>
        </button>

        <button
          onClick={() => navigate("/stock")}
          className="group relative rounded-2xl p-7 text-left transition-all duration-200 overflow-hidden hover:scale-[1.02]"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid var(--border)",
          }}
        >
          <div
            className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
            style={{
              background:
                "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.03), transparent 70%)",
            }}
          />
          <div className="relative">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center mb-5 text-lg"
              style={{ background: "rgba(255,255,255,0.06)" }}
            >
              📈
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">
              股票行情分析
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              即時股價、技術指標及基本面財務數據
            </p>
          </div>
          <div className="absolute bottom-5 right-5 text-slate-700 group-hover:text-slate-500 transition-colors text-xl">
            →
          </div>
        </button>
      </div>

      {/* Quick stock chips */}
      <div className="mb-14">
        <h2 className="text-xs font-medium text-slate-600 mb-4 tracking-widest uppercase">
          快速查詢股票
        </h2>
        <div className="flex flex-wrap gap-3">
          {quickStocks.map((symbol) => (
            <button
              key={symbol}
              onClick={() => navigate(`/stock/${symbol}`)}
              className="px-5 py-2 rounded-full text-xs font-medium text-slate-400 hover:text-slate-100 transition-all hover:scale-105"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border)",
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLElement).style.borderColor =
                  "rgba(99,102,241,0.4)";
                (e.target as HTMLElement).style.boxShadow =
                  "0 0 12px rgba(99,102,241,0.15)";
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLElement).style.borderColor = "var(--border)";
                (e.target as HTMLElement).style.boxShadow = "none";
              }}
            >
              {symbol}
            </button>
          ))}
        </div>
      </div>

      {/* Quick questions */}
      <div>
        <h2 className="text-xs font-medium text-slate-600 mb-4 tracking-widest uppercase">
          常見投資問題
        </h2>
        <div className="space-y-3">
          {quickQuestions.map((q, i) => (
            <button
              key={q}
              onClick={() =>
                navigate("/chat", { state: { initialMessage: q } })
              }
              className="group w-full text-left px-5 py-4 rounded-2xl text-sm text-slate-400 hover:text-slate-100 transition-all flex items-center justify-between"
              style={{
                background: "rgba(255,255,255,0.025)",
                border: "1px solid var(--border)",
                animationDelay: `${i * 60}ms`,
              }}
            >
              <div className="flex items-center gap-3">
                <span className="w-5 h-5 rounded-lg flex items-center justify-center text-xs text-indigo-400/60 group-hover:text-indigo-400 transition-colors font-mono">
                  {i + 1}
                </span>
                <span>{q}</span>
              </div>
              <svg
                viewBox="0 0 16 16"
                fill="currentColor"
                className="w-3.5 h-3.5 text-slate-700 group-hover:text-slate-400 group-hover:translate-x-0.5 transition-all flex-shrink-0"
              >
                <path
                  fillRule="evenodd"
                  d="M4 8a.5.5 0 01.5-.5h5.793L8.146 5.354a.5.5 0 11.708-.708l3 3a.5.5 0 010 .708l-3 3a.5.5 0 01-.708-.708L10.293 8.5H4.5A.5.5 0 014 8z"
                />
              </svg>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
