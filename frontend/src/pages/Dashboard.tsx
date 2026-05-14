import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getFeatureAccess } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useTokenClaims } from "@/lib/useTokenClaims";

const quickQuestions = [
  "什麼是 RSI 指標？",
  "MACD 如何判斷買賣點？",
  "移動平均線的使用方式？",
  "如何計算本益比？",
];

type FeatureCard = {
  featureKey: string;
  to: string;
  emoji: string;
  title: string;
  description: string;
  iconBg: string;
  cardBg: string;
  cardBorder: string;
  glow: string;
  arrowClass: string;
};

const featureCards: FeatureCard[] = [
  {
    featureKey: "chat",
    to: "/chat",
    emoji: "💬",
    title: "開始 AI 對話",
    description: "向 AI 提問投資策略、技術指標、個股分析",
    iconBg: "rgba(99,102,241,0.25)",
    cardBg:
      "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.12))",
    cardBorder: "1px solid rgba(99,102,241,0.25)",
    glow: "radial-gradient(circle at 50% 50%, rgba(99,102,241,0.12), transparent 70%)",
    arrowClass:
      "text-indigo-400/50 group-hover:text-indigo-400 transition-colors",
  },
  {
    featureKey: "stock",
    to: "/stock",
    emoji: "📈",
    title: "股票行情分析",
    description: "即時股價、技術指標及基本面財務數據",
    iconBg: "var(--overlay-subtle)",
    cardBg: "var(--card-bg)",
    cardBorder: "1px solid var(--border)",
    glow: "radial-gradient(circle at 50% 50%, var(--card-bg-hover), transparent 70%)",
    arrowClass: "text-slate-700 group-hover:text-slate-500 transition-colors",
  },
  {
    featureKey: "portfolio",
    to: "/portfolio",
    emoji: "💼",
    title: "投資組合",
    description: "追蹤持股表現、損益與資產配置",
    iconBg: "rgba(16,185,129,0.22)",
    cardBg:
      "linear-gradient(135deg, rgba(16,185,129,0.18), rgba(5,150,105,0.08))",
    cardBorder: "1px solid rgba(16,185,129,0.22)",
    glow: "radial-gradient(circle at 50% 50%, rgba(16,185,129,0.1), transparent 70%)",
    arrowClass:
      "text-emerald-400/50 group-hover:text-emerald-400 transition-colors",
  },
  {
    featureKey: "backtest",
    to: "/backtest",
    emoji: "📊",
    title: "策略回測",
    description: "用歷史數據驗證均線交叉、RSI、MACD 策略績效",
    iconBg: "rgba(245,158,11,0.2)",
    cardBg:
      "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(251,191,36,0.06))",
    cardBorder: "1px solid rgba(245,158,11,0.2)",
    glow: "radial-gradient(circle at 50% 50%, rgba(245,158,11,0.08), transparent 70%)",
    arrowClass:
      "text-amber-600/50 group-hover:text-amber-500 transition-colors",
  },
  {
    featureKey: "screener",
    to: "/screener",
    emoji: "🔍",
    title: "智能選股",
    description: "依條件篩選潛力股，快速找到符合策略的標的",
    iconBg: "rgba(34,211,238,0.2)",
    cardBg:
      "linear-gradient(135deg, rgba(34,211,238,0.16), rgba(14,165,233,0.08))",
    cardBorder: "1px solid rgba(34,211,238,0.22)",
    glow: "radial-gradient(circle at 50% 50%, rgba(34,211,238,0.1), transparent 70%)",
    arrowClass: "text-cyan-400/50 group-hover:text-cyan-400 transition-colors",
  },
];

export default function Dashboard() {
  const { user } = useAuthStore();
  const claims = useTokenClaims();
  const [allowedFeatures, setAllowedFeatures] = useState<Set<string> | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    getFeatureAccess()
      .then((data) => {
        if (cancelled) return;
        setAllowedFeatures(
          new Set(
            data.features
              .filter((feature) => feature.allowed)
              .map((feature) => feature.feature_key),
          ),
        );
      })
      .catch(() => {
        if (cancelled) return;
        setAllowedFeatures(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.uid]);

  // rerender-simple-expression-in-memo: trivial expression, no memo needed
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "早安" : hour < 18 ? "午安" : "晚安";

  const visibleCards = featureCards.filter(
    (card) =>
      claims.admin ||
      allowedFeatures === null ||
      allowedFeatures.has(card.featureKey),
  );

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="mb-8 md:mb-14">
        <p className="text-sm text-slate-600 mb-3 tracking-widest uppercase">
          {new Date().toLocaleDateString("zh-TW", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1
          className="text-2xl md:text-3xl font-semibold text-slate-100"
          style={{ textWrap: "balance" }}
        >
          {greeting}，
          <span className="gradient-text">{user?.displayName ?? "投資人"}</span>
        </h1>
        <p className="text-slate-500 text-sm mt-3">
          歡迎使用 Navi AI 投資分析助理
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5 mb-10 md:mb-14">
        {visibleCards.map((card) => (
          <Link
            key={card.featureKey}
            to={card.to}
            className="group relative rounded-2xl p-7 text-left transition-transform duration-200 overflow-hidden hover:scale-[1.02]"
            style={{
              background: card.cardBg,
              border: card.cardBorder,
            }}
          >
            <div
              className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
              style={{ background: card.glow }}
            />
            <div className="relative">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center mb-5 text-lg"
                style={{ background: card.iconBg }}
              >
                {card.emoji}
              </div>
              <h3 className="text-base font-semibold text-white mb-2.5">
                {card.title}
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                {card.description}
              </p>
            </div>
            <div
              className={`absolute bottom-5 right-5 text-xl ${card.arrowClass}`}
              aria-hidden="true"
            >
              →
            </div>
          </Link>
        ))}
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
                background: "var(--card-bg)",
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
