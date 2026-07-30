import { useState } from "react";
import { fmtCompactTWD } from "@/lib/format";
import type { PopularData, PopularStockItem } from "@/types/stock";

interface PopularStocksProps {
  data: PopularData;
  onSelect: (ticker: string, label: string) => void;
}

/** 台股慣例：紅漲綠跌（與 PriceChart 一致，勿改成歐美的綠漲紅跌）。 */
const UP = "var(--market-up)";
const DOWN = "var(--market-down)";

/**
 * 迷你走勢圖。手刻 SVG 而非用 recharts：這裡有 8 張卡各一條線，
 * 為此載入 ~340 kB 的圖表庫並不划算，何況使用者還沒查任何個股。
 */
function Sparkline({ values, up }: { values: number[]; up: boolean }) {
  if (values.length < 2) return <div className="h-7" />;

  const w = 100;
  const h = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1; // 一個月完全沒波動時避免除以 0
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="w-full h-7"
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={up ? UP : DOWN}
        strokeWidth="1.5"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function StockCard({
  item,
  onSelect,
}: {
  item: PopularStockItem;
  onSelect: (ticker: string, label: string) => void;
}) {
  const up = (item.change_percent ?? 0) >= 0;
  const pct = item.change_percent;

  return (
    <button
      onClick={() => onSelect(item.ticker, `${item.code} ${item.name}`)}
      className="text-left card card-hover p-4"
    >
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="text-sm font-bold text-ink-strong tabular-nums">{item.code}</span>
        <span className="text-[11px] text-ink-muted truncate">{item.name}</span>
      </div>
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <span className="text-base font-semibold text-ink tabular-nums">
          {item.price?.toLocaleString("en-US", { maximumFractionDigits: 2 }) ?? "-"}
        </span>
        <span
          className="text-xs font-semibold tabular-nums"
          style={{ color: up ? UP : DOWN }}
        >
          {pct == null ? "-" : `${up ? "+" : ""}${pct.toFixed(2)}%`}
        </span>
      </div>
      <Sparkline values={item.spark} up={up} />
      <div className="mt-1.5 text-[10px] text-ink-faint tabular-nums">
        成交值 {fmtCompactTWD(item.turnover)}
      </div>
    </button>
  );
}

export default function PopularStocks({ data, onSelect }: PopularStocksProps) {
  const [activeKey, setActiveKey] = useState(data.boards[0]?.key ?? "turnover");
  const board = data.boards.find((b) => b.key === activeKey) ?? data.boards[0];

  if (!board) return null;

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="flex items-baseline gap-2.5">
          <h2 className="text-sm font-semibold text-ink">熱門標的</h2>
          {data.as_of_date && (
            <span className="text-[11px] text-ink-faint tabular-nums">
              {data.as_of_date} 收盤
            </span>
          )}
        </div>
        <div className="flex gap-0.5 p-1 rounded-xl bg-[var(--surface-2)] border border-line-subtle">
          {data.boards.map((b) => (
            <button
              key={b.key}
              onClick={() => setActiveKey(b.key)}
              aria-pressed={b.key === activeKey}
              className={`shrink-0 px-3.5 py-1 rounded-lg text-[11px] font-semibold tracking-wide transition-colors ${
                b.key === activeKey
                  ? "text-ink border border-line-strong"
                  : "text-ink-muted border border-transparent"
              }`}
              style={
                b.key === activeKey ? { background: "var(--accent-soft)" } : undefined
              }
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {board.items.map((item) => (
          <StockCard key={item.ticker} item={item} onSelect={onSelect} />
        ))}
      </div>

      {data.note && (
        <p className="mt-4 text-[10px] text-ink-faint leading-relaxed">{data.note}</p>
      )}
    </div>
  );
}
