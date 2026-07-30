import { useStockNews } from "@/lib/queries/stock";

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
  // 新聞快取 30 分鐘（對齊後端 TTL）：在分頁之間來回切不會重打 RSS
  const { data, isLoading, isError } = useStockNews(ticker, 10);

  const articles = data?.articles ?? [];
  const error = isError
    ? "新聞載入失敗，請稍後再試"
    : data && articles.length === 0
      ? data.error || "暫無相關新聞"
      : "";
  const loading = isLoading;

  if (loading) {
    return (
      <div className="card p-8 text-center text-sm text-ink-muted">
        新聞載入中…
      </div>
    );
  }

  if (articles.length === 0) {
    return (
      <div className="card p-8 text-center text-sm text-ink-muted">
        {error || "暫無相關新聞"}
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <ul className="divide-y divide-line-subtle">
        {articles.map((a, i) => (
          <li key={i} className="px-6 py-4">
            <a
              href={a.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-ink hover:text-accent transition-colors leading-relaxed"
            >
              {a.title}
            </a>
            <div className="flex items-center gap-2 mt-2 text-xs text-ink-muted">
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
