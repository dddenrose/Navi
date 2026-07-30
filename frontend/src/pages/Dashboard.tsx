import { useRef, type CSSProperties, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import {
  MessageSquare,
  TrendingUp,
  Briefcase,
  ScanSearch,
  type LucideIcon,
} from "lucide-react";
import { useAllowedFeatures } from "@/lib/queries/account";
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
  icon: LucideIcon;
  title: string;
  description: string;
};

const featureCards: FeatureCard[] = [
  {
    featureKey: "chat",
    to: "/chat",
    icon: MessageSquare,
    title: "開始 AI 對話",
    description: "向 AI 提問投資策略、技術指標、個股分析",
  },
  {
    featureKey: "stock",
    to: "/stock",
    icon: TrendingUp,
    title: "股票行情分析",
    description: "即時股價、技術指標及基本面財務數據",
  },
  {
    featureKey: "portfolio",
    to: "/portfolio",
    icon: Briefcase,
    title: "投資組合",
    description: "追蹤持股表現、損益與資產配置",
  },
  {
    featureKey: "screener",
    to: "/screener",
    icon: ScanSearch,
    title: "智能選股",
    description: "依條件篩選潛力股，快速找到符合策略的標的",
  },
];

/** 游標跟隨微光的卡片（--mx/--my 是動態值，只有這裡例外使用 inline style）。 */
function FeatureCardLink({
  card,
  revealIndex,
}: {
  card: FeatureCard;
  revealIndex: number;
}) {
  const ref = useRef<HTMLAnchorElement>(null);
  const Icon = card.icon;

  const handleMouseMove = (e: MouseEvent<HTMLAnchorElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
    el.style.setProperty("--my", `${e.clientY - rect.top}px`);
  };

  return (
    <Link
      ref={ref}
      to={card.to}
      onMouseMove={handleMouseMove}
      className="card card-hover card-spotlight reveal relative block p-7 text-left"
      style={{ "--reveal-i": revealIndex } as CSSProperties}
    >
      <div className="relative">
        <div className="w-10 h-10 rounded-chip flex items-center justify-center mb-5 bg-[var(--accent-soft)] text-accent">
          <Icon className="w-5 h-5" strokeWidth={1.7} aria-hidden="true" />
        </div>
        <h3 className="text-base font-semibold text-ink-strong mb-2.5">
          {card.title}
        </h3>
        <p className="text-sm text-ink-secondary leading-relaxed">
          {card.description}
        </p>
      </div>
    </Link>
  );
}

export default function Dashboard() {
  const { user } = useAuthStore();
  const claims = useTokenClaims();
  // 與 Layout、FeatureGuard 共用同一份權限快取（見 lib/queries/account.ts）
  const allowedFeatures = useAllowedFeatures();

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
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-5xl mx-auto">
      {/* Header */}
      <div
        className="mb-8 md:mb-14 reveal"
        style={{ "--reveal-i": 0 } as CSSProperties}
      >
        <p className="text-sm text-ink-muted mb-3 tracking-widest uppercase">
          {new Date().toLocaleDateString("zh-TW", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1
          className="text-2xl md:text-3xl font-semibold text-ink-strong"
          style={{ textWrap: "balance" }}
        >
          {greeting}，
          <span className="text-signature">
            {user?.displayName ?? "投資人"}
          </span>
        </h1>
        <p className="text-ink-muted text-sm mt-3">
          歡迎使用 Navi AI 投資分析助理
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5 mb-10 md:mb-14">
        {visibleCards.map((card, i) => (
          <FeatureCardLink key={card.featureKey} card={card} revealIndex={i + 1} />
        ))}
      </div>

      {/* Quick questions */}
      <div className="reveal" style={{ "--reveal-i": 5 } as CSSProperties}>
        <h2
          className="text-xs font-medium text-ink-muted mb-5 tracking-widest uppercase"
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
              className="group w-full text-left px-5 py-4 rounded-2xl text-sm text-ink-secondary hover:text-ink-strong transition-colors flex items-center justify-between border border-line-subtle hover:border-line"
            >
              <div className="flex items-center gap-4">
                <span className="w-6 h-6 rounded-lg flex items-center justify-center text-xs text-accent/60 group-hover:text-accent transition-colors font-mono flex-shrink-0">
                  {i + 1}
                </span>
                <span>{q}</span>
              </div>
              <svg
                viewBox="0 0 16 16"
                fill="currentColor"
                className="w-3.5 h-3.5 text-ink-faint group-hover:text-ink-muted group-hover:translate-x-0.5 transition-[color,transform] flex-shrink-0"
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
