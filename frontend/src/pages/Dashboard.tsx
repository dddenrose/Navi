import { Link } from "react-router-dom";
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

  // rerender-simple-expression-in-memo: trivial expression, no memo needed
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "早安" : hour < 18 ? "午安" : "晚安";

  return (
    <div className="px-10 py-10 max-w-4xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="mb-14">
        <p className="text-sm text-slate-600 mb-3 tracking-widest uppercase">
          {new Date().toLocaleDateString("zh-TW", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1
          className="text-3xl font-semibold text-slate-100"
          style={{ textWrap: "balance" }}
        >
          {greeting}，
          <span className="gradient-text">{user?.displayName ?? "投資人"}</span>
        </h1>
        <p className="text-slate-500 text-sm mt-3">
          歡迎使用 Navi AI 投資分析助理
        </p>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-14">
        <Link
          to="/chat"
          className="group relative rounded-2xl p-7 text-left transition-transform duration-200 overflow-hidden hover:scale-[1.02]"
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
            <h3 className="text-base font-semibold text-white mb-2.5">
              開始 AI 對話
            </h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              向 AI 提問投資策略、技術指標、個股分析
            </p>
          </div>
          <div
            className="absolute bottom-5 right-5 text-indigo-400/50 group-hover:text-indigo-400 transition-colors text-xl"
            aria-hidden="true"
          >
            →
          </div>
        </Link>

        <Link
          to="/stock"
          className="group relative rounded-2xl p-7 text-left transition-transform duration-200 overflow-hidden hover:scale-[1.02]"
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
            <h3 className="text-base font-semibold text-white mb-2.5">
              股票行情分析
            </h3>
            <p className="text-sm text-slate-500 leading-relaxed">
              即時股價、技術指標及基本面財務數據
            </p>
          </div>
          <div
            className="absolute bottom-5 right-5 text-slate-700 group-hover:text-slate-500 transition-colors text-xl"
            aria-hidden="true"
          >
            →
          </div>
        </Link>
      </div>

      {/* Quick stock chips */}
      <div className="mb-14">
        <h2
          className="text-xs font-medium text-slate-600 mb-5 tracking-widest uppercase"
          style={{ textWrap: "balance" }}
        >
          快速查詢股票
        </h2>
        <div className="flex flex-wrap gap-3">
          {quickStocks.map((symbol) => (
            <Link
              key={symbol}
              to={`/stock/${symbol}`}
              className="stock-chip px-5 py-2 rounded-full text-xs font-medium text-slate-400 hover:text-slate-100 hover:scale-105"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border)",
              }}
            >
              {symbol}
            </Link>
          ))}
        </div>
      </div>

      {/* Quick questions */}
      <div>
        <h2
          className="text-xs font-medium text-slate-600 mb-5 tracking-widest uppercase"
          style={{ textWrap: "balance" }}
        >
          常見投資問題
        </h2>
        <div className="space-y-3">
          {quickQuestions.map((q, i) => (
            <Link
              key={q}
              to="/chat"
              state={{ initialMessage: q }}
              className="group w-full text-left px-5 py-4 rounded-2xl text-sm text-slate-400 hover:text-slate-100 transition-colors flex items-center justify-between"
              style={{
                background: "rgba(255,255,255,0.025)",
                border: "1px solid var(--border)",
                animationDelay: `${i * 60}ms`,
              }}
            >
              <div className="flex items-center gap-4">
                <span className="w-6 h-6 rounded-lg flex items-center justify-center text-xs text-indigo-400/60 group-hover:text-indigo-400 transition-colors font-mono flex-shrink-0">
                  {i + 1}
                </span>
                <span>{q}</span>
              </div>
              <svg
                viewBox="0 0 16 16"
                fill="currentColor"
                className="w-3.5 h-3.5 text-slate-700 group-hover:text-slate-400 group-hover:translate-x-0.5 transition-[color,transform] flex-shrink-0"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M4 8a.5.5 0 01.5-.5h5.793L8.146 5.354a.5.5 0 11.708-.708l3 3a.5.5 0 010 .708l-3 3a.5.5 0 01-.708-.708L10.293 8.5H4.5A.5.5 0 014 8z"
                />
              </svg>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
