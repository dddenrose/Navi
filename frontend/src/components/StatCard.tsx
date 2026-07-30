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
  valueColor = "text-ink",
}: StatCardProps) {
  return (
    <div className="card p-5">
      <p className="text-xs text-ink-muted mb-2">{label}</p>
      <p className={`text-sm font-semibold tabular-nums ${valueColor}`}>
        {value}
      </p>
    </div>
  );
});

export default StatCard;
