import StatCard from "@/components/StatCard";
import { fmtNum, fmtPct, fmtPrice } from "@/lib/format";
import {
  useStockIndustryPe,
  useStockMonthlyRevenue,
} from "@/lib/queries/stock";
import type { Fundamentals } from "@/types/stock";

interface StockFundamentalTabProps {
  fundamentalData: Fundamentals;
  currency: string;
  ticker: string;
}

/** 月營收單位為「仟元」；轉換為台股慣用的「億元」顯示。 */
function fmtRevenue(thousands: number | null): string {
  if (thousands == null) return "-";
  const yi = (thousands * 1000) / 1e8;
  return `${yi.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} 億元`;
}

export default function StockFundamentalTab({
  fundamentalData,
  currency,
  ticker,
}: StockFundamentalTabProps) {
  // 月營收快照與產業 PE 分位數：兩者皆為可選的加值資訊，各自獨立 lazy fetch
  // （進到基本面分頁才打），查無資料時整塊靜默隱藏，不顯示錯誤——失敗時
  // query 的 data 是 undefined，下方的條件渲染自然就跳過了。
  // 換股票時 query key 跟著換，不會拿到上一檔的殘留資料。
  const monthlyRevenue = useStockMonthlyRevenue(ticker).data ?? null;
  const industryPe = useStockIndustryPe(ticker).data ?? null;

  const valuationBands = [
    {
      label: "便宜價",
      dot: "var(--market-down)",
      value:
        fundamentalData.cheap_price != null
          ? fmtPrice(fundamentalData.cheap_price, currency)
          : "-",
      color: "text-down",
    },
    {
      label: "合理價",
      dot: "var(--warn)",
      value: fmtPrice(fundamentalData.fair_price, currency),
      color: "text-warn",
    },
    {
      label: "昂貴價",
      dot: "var(--market-up)",
      value:
        fundamentalData.expensive_price != null
          ? fmtPrice(fundamentalData.expensive_price, currency)
          : "-",
      color: "text-up",
    },
  ];

  return (
    <div className="space-y-6">
      {/* 公司簡介 */}
      {fundamentalData.description && (
        <div className="card p-6">
          <p className="text-xs text-ink-muted mb-3">公司簡介</p>
          <p className="text-sm text-ink leading-loose line-clamp-4">
            {fundamentalData.description}
          </p>
          {(fundamentalData.sector || fundamentalData.industry) && (
            <div className="flex gap-3 mt-5">
              {fundamentalData.sector && (
                <span className="px-3 py-1.5 bg-accent/10 border border-accent/20 text-accent text-xs rounded-full">
                  {fundamentalData.sector}
                </span>
              )}
              {fundamentalData.industry && (
                <span className="px-3 py-1.5 bg-[var(--surface-3)] text-ink-secondary text-xs rounded-full">
                  {fundamentalData.industry}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* 估值指標 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
        {[
          { label: "本益比 (P/E)", value: fmtNum(fundamentalData.pe_ratio) },
          { label: "預期本益比", value: fmtNum(fundamentalData.forward_pe) },
          {
            label: "股價淨值比 (P/B)",
            value: fmtNum(fundamentalData.pb_ratio),
          },
          { label: "殖利率", value: fmtPct(fundamentalData.dividend_yield) },
          {
            label: "EPS (TTM)",
            value:
              fundamentalData.eps != null ? fmtNum(fundamentalData.eps) : "-",
          },
          {
            label: "預期 EPS",
            value:
              fundamentalData.forward_eps != null
                ? fmtNum(fundamentalData.forward_eps)
                : "-",
          },
          { label: "ROE", value: fmtPct(fundamentalData.roe) },
          { label: "ROA", value: fmtPct(fundamentalData.roa) },
          { label: "淨利率", value: fmtPct(fundamentalData.profit_margin) },
          {
            label: "營業利益率",
            value: fmtPct(fundamentalData.operating_margin),
          },
          { label: "營收成長", value: fmtPct(fundamentalData.revenue_growth) },
          { label: "獲利成長", value: fmtPct(fundamentalData.earnings_growth) },
        ].map(({ label, value }) => (
          <StatCard key={label} label={label} value={value} valueColor="text-ink-strong" />
        ))}
      </div>

      {/* 最新月營收快照（僅上市股票有資料；查無資料整塊靜默隱藏） */}
      {monthlyRevenue && (
        <div className="card p-6">
          <p className="text-xs text-ink-muted mb-4">最新月營收</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
            <StatCard
              label="當月營收"
              value={fmtRevenue(monthlyRevenue.revenue)}
              valueColor="text-ink-strong"
            />
            <StatCard
              label="年增率 (YoY)"
              value={fmtPct(monthlyRevenue.yoy)}
              valueColor={
                (monthlyRevenue.yoy ?? 0) > 0
                  ? "text-up"
                  : (monthlyRevenue.yoy ?? 0) < 0
                    ? "text-down"
                    : "text-ink-strong"
              }
            />
            <StatCard
              label="月增率 (MoM)"
              value={fmtPct(monthlyRevenue.mom)}
              valueColor={
                (monthlyRevenue.mom ?? 0) > 0
                  ? "text-up"
                  : (monthlyRevenue.mom ?? 0) < 0
                    ? "text-down"
                    : "text-ink-strong"
              }
            />
            <StatCard
              label="累計營收年增率"
              value={fmtPct(monthlyRevenue.yoy_acc)}
              valueColor={
                (monthlyRevenue.yoy_acc ?? 0) > 0
                  ? "text-up"
                  : (monthlyRevenue.yoy_acc ?? 0) < 0
                    ? "text-down"
                    : "text-ink-strong"
              }
            />
          </div>
          {monthlyRevenue.label && (
            <p className="text-xs text-ink-faint mt-4">
              資料期間：{monthlyRevenue.label}（TWSE 公開資訊觀測站）
            </p>
          )}
        </div>
      )}

      {/* 合理價位估算 */}
      {fundamentalData.fair_price != null && (
        <div className="card p-6">
          <p className="text-xs text-ink-muted mb-4">合理價位估算（PE 法）</p>
          <div className="grid grid-cols-3 gap-4">
            {valuationBands.map(({ label, dot, value, color }) => (
              <div key={label} className="text-center">
                <p className="text-xs text-ink-muted mb-2 inline-flex items-center justify-center gap-1.5 w-full">
                  <span
                    className="inline-block w-2 h-2 rounded-full shrink-0"
                    style={{ background: dot }}
                    aria-hidden="true"
                  />
                  {label}
                </p>
                <p className={`text-base font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          {fundamentalData.valuation_note && (
            <p className="text-xs text-ink-faint mt-4 leading-relaxed">
              {fundamentalData.valuation_note}
            </p>
          )}
          {industryPe && (
            <p className="text-xs text-ink-muted mt-2 leading-relaxed">
              PE 位於同產業（{industryPe.industry}）第 {industryPe.percentile.toFixed(0)}{" "}
              百分位（樣本 {industryPe.sample_size} 檔）
            </p>
          )}
        </div>
      )}
    </div>
  );
}
