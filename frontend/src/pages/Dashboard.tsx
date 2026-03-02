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
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">
          {greeting()}，{user?.displayName ?? "投資人"} 👋
        </h1>
        <p className="text-slate-400 mt-1">歡迎使用 Navi AI 投資分析助理</p>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        <button
          onClick={() => navigate("/chat")}
          className="bg-indigo-600 hover:bg-indigo-500 rounded-xl p-5 text-left transition-colors group"
        >
          <div className="text-2xl mb-2">💬</div>
          <h3 className="text-white font-semibold">開始對話</h3>
          <p className="text-indigo-200 text-sm mt-1">向 AI 提問投資相關問題</p>
        </button>
        <button
          onClick={() => navigate("/stock")}
          className="bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl p-5 text-left transition-colors group"
        >
          <div className="text-2xl mb-2">📈</div>
          <h3 className="text-white font-semibold">股票分析</h3>
          <p className="text-slate-400 text-sm mt-1">
            查詢股票技術與基本面數據
          </p>
        </button>
      </div>

      {/* Quick stock links */}
      <div className="mb-8">
        <h2 className="text-sm font-medium text-slate-400 mb-3 uppercase tracking-wider">
          快速查詢股票
        </h2>
        <div className="flex flex-wrap gap-2">
          {quickStocks.map((symbol) => (
            <button
              key={symbol}
              onClick={() => navigate(`/stock/${symbol}`)}
              className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-full text-sm text-slate-300 hover:text-white transition-colors"
            >
              {symbol}
            </button>
          ))}
        </div>
      </div>

      {/* Quick questions */}
      <div>
        <h2 className="text-sm font-medium text-slate-400 mb-3 uppercase tracking-wider">
          常見問題
        </h2>
        <div className="space-y-2">
          {quickQuestions.map((q) => (
            <button
              key={q}
              onClick={() =>
                navigate("/chat", { state: { initialMessage: q } })
              }
              className="w-full text-left px-4 py-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-sm text-slate-300 hover:text-white transition-colors flex items-center justify-between group"
            >
              <span>{q}</span>
              <span className="text-slate-600 group-hover:text-slate-400">
                →
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
