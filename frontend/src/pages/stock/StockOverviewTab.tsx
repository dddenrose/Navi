import StatCard from "@/components/StatCard";
import { fmtLarge, fmtPrice } from "@/lib/format";
import type { StockPrice } from "@/types/stock";

interface StockOverviewTabProps {
  priceData: StockPrice;
  currency: string;
}

export default function StockOverviewTab({
  priceData,
  currency,
}: StockOverviewTabProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
      {[
        {
          label: "成交量",
          value: priceData.volume?.toLocaleString() ?? "-",
        },
        {
          label: "市值",
          value: fmtLarge(priceData.market_cap, currency),
        },
        {
          label: "52週高點",
          value:
            priceData.high_52w != null
              ? fmtPrice(priceData.high_52w, currency)
              : "-",
        },
        {
          label: "52週低點",
          value:
            priceData.low_52w != null
              ? fmtPrice(priceData.low_52w, currency)
              : "-",
        },
      ].map(({ label, value }) => (
        // rerender-memo: StatCard is memoized
        <StatCard key={label} label={label} value={value} />
      ))}
    </div>
  );
}
