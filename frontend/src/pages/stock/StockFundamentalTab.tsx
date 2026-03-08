import StatCard from "@/components/StatCard";
import { fmtNum, fmtPct, fmtPrice } from "@/lib/format";
import type { Fundamentals } from "@/types/stock";

interface StockFundamentalTabProps {
  fundamentalData: Fundamentals;
  currency: string;
}

export default function StockFundamentalTab({
  fundamentalData,
  currency,
}: StockFundamentalTabProps) {
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
        </div>
      )}
    </div>
  );
}
