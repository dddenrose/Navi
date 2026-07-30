import { memo, useState } from "react";
import type { ThinkingStep } from "@/lib/api";

// Module-level constant — avoid recreating on every render
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  get_stock_price: "查詢股價",
  analyze_technicals: "技術分析",
  analyze_fundamentals: "基本面分析",
  get_institutional: "法人籌碼",
  get_margin_trading: "融資融券",
  search_financial_news: "搜尋新聞",
  search_knowledge: "知識庫搜尋",
  run_strategy_backtest: "策略回測",
  get_portfolio: "投資組合",
};

const INTENT_DISPLAY_NAMES: Record<string, string> = {
  entry_analysis: "進場分析",
  comprehensive_analysis: "綜合分析",
  technical_analysis: "技術分析",
  fundamental_analysis: "基本面分析",
  price_query: "股價查詢",
  institutional_analysis: "籌碼分析",
  news: "新聞搜尋",
  portfolio: "投資組合",
  backtest: "策略回測",
  knowledge: "知識查詢",
  general: "一般對話",
};

function getToolName(tool: string): string {
  return TOOL_DISPLAY_NAMES[tool] ?? tool;
}

function getIntentName(intent: string): string {
  return INTENT_DISPLAY_NAMES[intent] ?? intent;
}

/* ── Minimal SVG icon components ── */

function SpinnerIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="8"
        cy="8"
        r="6"
        stroke="currentColor"
        strokeOpacity="0.2"
        strokeWidth="2"
      />
      <path
        d="M14 8a6 6 0 00-6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3.5 8.5L6.5 11.5L12.5 4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IntentIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
      <circle
        cx="8"
        cy="8"
        r="6.5"
        stroke="currentColor"
        strokeWidth="1"
        strokeOpacity="0.4"
      />
    </svg>
  );
}

interface ThinkingPanelProps {
  steps: ThinkingStep[];
  isStreaming: boolean;
}

export const ThinkingPanel = memo(function ThinkingPanel({
  steps,
  isStreaming,
}: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  // Build display steps: intent + tool_starts (tool_end merged into tool_start)
  const displaySteps = steps.filter((s) => s.type !== "tool_end");

  const completedTools = steps.filter((s) => s.type === "tool_end");
  const pendingTools = steps.filter(
    (s) =>
      s.type === "tool_start" &&
      !steps.some((e) => e.type === "tool_end" && e.tool === s.tool),
  );

  const isActive = isStreaming && pendingTools.length > 0;

  let summaryText: string;
  if (isActive) {
    summaryText = `分析中 · ${completedTools.length}/${completedTools.length + pendingTools.length} 完成`;
  } else if (completedTools.length > 0) {
    summaryText = `已完成 ${completedTools.length} 項分析`;
  } else {
    const intentStep = steps.find((s) => s.type === "intent");
    summaryText =
      intentStep && intentStep.type === "intent"
        ? `${getIntentName(intentStep.intent)}`
        : "思考中";
  }

  return (
    <div className="mb-2 text-xs">
      {/* Header toggle */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="group flex items-center gap-1.5 py-1.5 text-left transition-colors"
      >
        {/* Animated indicator */}
        <span className="flex-shrink-0 w-4 h-4 text-ink-muted">
          {isActive ? (
            <SpinnerIcon className="w-4 h-4" />
          ) : (
            <CheckIcon className="w-4 h-4" />
          )}
        </span>

        <span className="text-ink-muted group-hover:text-ink transition-colors">
          {summaryText}
        </span>

        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-3 h-3 text-ink-faint group-hover:text-ink-secondary transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {/* Expanded timeline */}
      {expanded && (
        <div className="ml-[7px] pl-4 pb-1 mt-0.5">
          {displaySteps.map((step, i) => {
            const isLast = i === displaySteps.length - 1;
            return (
              <div key={i} className="relative flex items-start gap-2 py-1">
                {/* Timeline dot */}
                <span
                  className={`absolute -left-[21px] top-[7px] w-[7px] h-[7px] rounded-full border ${
                    step.type === "tool_start" &&
                    !steps.some(
                      (e) => e.type === "tool_end" && e.tool === step.tool,
                    )
                      ? "border-ink-secondary bg-transparent"
                      : "border-ink-muted bg-ink-muted"
                  } ${isLast && isActive ? "animate-pulse" : ""}`}
                />

                {step.type === "intent" && (
                  <span className="text-ink-secondary flex items-center gap-1.5">
                    <IntentIcon className="w-3 h-3 text-ink-muted flex-shrink-0" />
                    <span className="text-ink-muted">意圖</span>
                    <span className="text-ink">
                      {getIntentName(step.intent)}
                    </span>
                    {step.ticker &&
                      step.ticker !== "null" &&
                      step.ticker !== "None" && (
                        <span className="text-ink-muted">{step.ticker}</span>
                      )}
                  </span>
                )}

                {step.type === "tool_start" && (
                  <span className="text-ink-secondary flex items-center gap-1.5">
                    {steps.some(
                      (e) => e.type === "tool_end" && e.tool === step.tool,
                    ) ? (
                      <CheckIcon className="w-3 h-3 text-emerald-500/70 flex-shrink-0" />
                    ) : (
                      <SpinnerIcon className="w-3 h-3 text-ink-secondary flex-shrink-0" />
                    )}
                    <span className="text-ink">
                      {getToolName(step.tool)}
                    </span>
                    {(() => {
                      const t = step.input?.ticker;
                      return typeof t === "string" && t ? (
                        <span className="text-ink-muted">{t}</span>
                      ) : null;
                    })()}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});
