import { useState, useEffect } from "react";
import { getAuthHeaders, getStockNews } from "@/lib/api";
import type { NewsArticle } from "@/types/stock";

interface StockNewsTabProps {
  ticker: string;
}

/** 把後端已格式化的 "YYYY/MM/DD HH:MM" 字串轉為相對時間顯示。 */
function relativeTime(published: string): string {
  if (!published) return "";
  const d = new Date(published.replace(/\//g, "-"));
  if (isNaN(d.getTime())) return published;
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "剛剛";
  if (diffMin < 60) return `${diffMin} 分鐘前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小時前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  return published; // 超過 30 天：顯示絕對時間比較有意義
}

export default function StockNewsTab({ ticker }: StockNewsTabProps) {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setArticles([]);

    (async () => {
      try {
        const headers = await getAuthHeaders();
        const data = await getStockNews(ticker, 10, headers);
        if (cancelled) return;
        setArticles(data.articles);
        if (data.articles.length === 0) setError(data.error || "暫無相關新聞");
      } catch {
        if (!cancelled) setError("新聞載入失敗，請稍後再試");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const cardStyle = {
    background: "var(--card-bg)",
    border: "1px solid var(--border)",
  };

  if (loading) {
    return (
      <div className="rounded-2xl p-8 text-center text-sm text-slate-500" style={cardStyle}>
        新聞載入中…
      </div>
    );
  }

  if (articles.length === 0) {
    return (
      <div className="rounded-2xl p-8 text-center text-sm text-slate-500" style={cardStyle}>
        {error || "暫無相關新聞"}
      </div>
    );
  }

  return (
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <ul className="divide-y divide-white/5">
        {articles.map((a, i) => (
          <li key={i} className="px-6 py-4">
            <a
              href={a.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-slate-200 hover:text-indigo-400 transition-colors leading-relaxed"
            >
              {a.title}
            </a>
            <div className="flex items-center gap-2 mt-2 text-xs text-slate-500">
              {a.source && <span>{a.source}</span>}
              {a.source && a.published && <span>·</span>}
              {a.published && <span>{relativeTime(a.published)}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
