import { memo, useState } from "react";
import type { Citation } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  price: "股價",
  technicals: "技術面",
  fundamentals: "基本面",
  institutional: "三大法人",
  margin: "融資融券",
  news: "新聞",
  knowledge: "知識庫",
  backtest: "回測",
  portfolio: "投資組合",
};

function getTypeLabel(t: string): string {
  return TYPE_LABELS[t] ?? t;
}

function formatFetchedAt(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

interface CitationsListProps {
  citations: Citation[];
}

export const CitationsList = memo(function CitationsList({
  citations,
}: CitationsListProps) {
  const [expanded, setExpanded] = useState(false);

  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-3 text-xs">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="group flex items-center gap-1.5 py-1 text-left transition-colors"
      >
        <svg
          viewBox="0 0 16 16"
          fill="none"
          className="w-3.5 h-3.5 text-slate-500"
          aria-hidden="true"
        >
          <path
            d="M6 2.5h5.5a1.5 1.5 0 011.5 1.5v9.5a1.5 1.5 0 01-1.5 1.5H4.5A1.5 1.5 0 013 13.5V5l3-2.5z"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
          <path
            d="M5.5 8.5h5M5.5 11h5M5.5 6h2"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
        <span className="text-slate-500 group-hover:text-slate-300 transition-colors">
          資料來源 · {citations.length} 筆
        </span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-3 h-3 text-slate-600 group-hover:text-slate-400 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {expanded && (
        <ol className="mt-1 ml-1 space-y-1.5 list-none">
          {citations.map((c) => (
            <li
              key={c.id}
              className="flex gap-2 text-slate-400 leading-relaxed"
            >
              <span className="flex-shrink-0 text-slate-600 tabular-nums">
                [{c.id}]
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-1.5">
                  <span className="text-slate-500">{getTypeLabel(c.type)}</span>
                  {c.url ? (
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-400 hover:text-indigo-300 hover:underline break-all"
                    >
                      {c.title || c.source}
                    </a>
                  ) : (
                    <span className="text-slate-300">
                      {c.title || c.source}
                    </span>
                  )}
                  {c.title && c.source && (
                    <span className="text-slate-600">· {c.source}</span>
                  )}
                  {c.fetched_at && (
                    <span className="text-slate-600 tabular-nums">
                      · 取得於 {formatFetchedAt(c.fetched_at)}
                    </span>
                  )}
                </div>
                {c.note && (
                  <div className="text-slate-600 text-[11px] mt-0.5">
                    ⚠️ {c.note}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
});
