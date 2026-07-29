import { useState, useEffect } from "react";
import StatCard from "@/components/StatCard";
import { fmtNum, fmtPct, fmtPrice } from "@/lib/format";
import {
  getAuthHeaders,
  getStockMonthlyRevenue,
  getStockIndustryPe,
} from "@/lib/api";
import type { Fundamentals, MonthlyRevenueData, IndustryPeData } from "@/types/stock";

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
  // 月營收快照與產業 PE 分位數：兩者皆為可選的加值資訊，
  // 各自獨立 lazy fetch（進到基本面分頁才打），查無資料時整塊靜默隱藏，不顯示錯誤。
  // state 帶 ticker 一起存，render 時比對即可濾掉換股後的舊資料，
  // 不需要在 effect 裡同步 setState 重置。
  const [extras, setExtras] = useState<{
    ticker: string;
    monthlyRevenue: MonthlyRevenueData | null;
    industryPe: IndustryPeData | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const headers = await getAuthHeaders();
        const [revResult, peResult] = await Promise.allSettled([
          getStockMonthlyRevenue(ticker, headers),
          getStockIndustryPe(ticker, headers),
        ]);
        if (cancelled) return;
        setExtras({
          ticker,
          monthlyRevenue:
            revResult.status === "fulfilled" ? revResult.value : null,
          industryPe: peResult.status === "fulfilled" ? peResult.value : null,
        });
      } catch {
        // 靜默失敗：這兩項都是加值資訊，缺資料不影響基本面分頁其餘內容
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const monthlyRevenue =
    extras?.ticker === ticker ? extras.monthlyRevenue : null;
  const industryPe = extras?.ticker === ticker ? extras.industryPe : null;

  return (
    <div className="space-y-6">
      {/* 公司簡介 */}
      {fundamentalData.description && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-xs text-slate-500 mb-3">公司簡介</p>
          <p className="text-sm text-slate-300 leading-loose line-clamp-4">
            {fundamentalData.description}
          </p>
          {(fundamentalData.sector || fundamentalData.industry) && (
            <div className="flex gap-3 mt-5">
              {fundamentalData.sector && (
                <span className="px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs rounded-full">
                  {fundamentalData.sector}
                </span>
              )}
              {fundamentalData.industry && (
                <span className="px-3 py-1.5 bg-slate-700 text-slate-400 text-xs rounded-full">
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
          <StatCard
            key={label}
            label={label}
            value={value}
            valueColor="text-slate-100"
          />
        ))}
      </div>

      {/* 最新月營收快照（僅上市股票有資料；查無資料整塊靜默隱藏） */}
      {monthlyRevenue && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-xs text-slate-500 mb-4">最新月營收</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
            <StatCard
              label="當月營收"
              value={fmtRevenue(monthlyRevenue.revenue)}
              valueColor="text-slate-100"
            />
            <StatCard
              label="年增率 (YoY)"
              value={fmtPct(monthlyRevenue.yoy)}
              valueColor={
                (monthlyRevenue.yoy ?? 0) > 0
                  ? "text-red-400"
                  : (monthlyRevenue.yoy ?? 0) < 0
                    ? "text-green-400"
                    : "text-slate-100"
              }
            />
            <StatCard
              label="月增率 (MoM)"
              value={fmtPct(monthlyRevenue.mom)}
              valueColor={
                (monthlyRevenue.mom ?? 0) > 0
                  ? "text-red-400"
                  : (monthlyRevenue.mom ?? 0) < 0
                    ? "text-green-400"
                    : "text-slate-100"
              }
            />
            <StatCard
              label="累計營收年增率"
              value={fmtPct(monthlyRevenue.yoy_acc)}
              valueColor={
                (monthlyRevenue.yoy_acc ?? 0) > 0
                  ? "text-red-400"
                  : (monthlyRevenue.yoy_acc ?? 0) < 0
                    ? "text-green-400"
                    : "text-slate-100"
              }
            />
          </div>
          {monthlyRevenue.label && (
            <p className="text-xs text-slate-600 mt-4">
              資料期間：{monthlyRevenue.label}（TWSE 公開資訊觀測站）
            </p>
          )}
        </div>
      )}

      {/* 合理價位估算 */}
      {fundamentalData.fair_price != null && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-xs text-slate-500 mb-4">合理價位估算（PE 法）</p>
          <div className="grid grid-cols-3 gap-4">
            {[
              {
                label: "🟢 便宜價",
                value:
                  fundamentalData.cheap_price != null
                    ? fmtPrice(fundamentalData.cheap_price, currency)
                    : "-",
                color: "text-green-400",
              },
              {
                label: "🟡 合理價",
                value: fmtPrice(fundamentalData.fair_price, currency),
                color: "text-yellow-400",
              },
              {
                label: "🔴 昂貴價",
                value:
                  fundamentalData.expensive_price != null
                    ? fmtPrice(fundamentalData.expensive_price, currency)
                    : "-",
                color: "text-red-400",
              },
            ].map(({ label, value, color }) => (
              <div key={label} className="text-center">
                <p className="text-xs text-slate-500 mb-2">{label}</p>
                <p className={`text-base font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          {fundamentalData.valuation_note && (
            <p className="text-xs text-slate-600 mt-4 leading-relaxed">
              {fundamentalData.valuation_note}
            </p>
          )}
          {industryPe && (
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              PE 位於同產業（{industryPe.industry}）第 {industryPe.percentile.toFixed(0)}{" "}
              百分位（樣本 {industryPe.sample_size} 檔）
            </p>
          )}
        </div>
      )}
    </div>
  );
}
