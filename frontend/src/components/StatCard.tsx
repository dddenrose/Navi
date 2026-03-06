import { memo } from "react";

interface StatCardProps {
  label: string;
  value: string;
  valueColor?: string;
}

// Memoized to prevent re-renders when parent state changes but props stay same
const StatCard = memo(function StatCard({
  label,
  value,
  valueColor = "text-slate-200",
}: StatCardProps) {
  return (
    <div
      className="rounded-2xl p-5"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <p className="text-xs text-slate-500 mb-2">{label}</p>
      <p className={`text-sm font-semibold tabular-nums ${valueColor}`}>
        {value}
      </p>
    </div>
  );
});

export default StatCard;
