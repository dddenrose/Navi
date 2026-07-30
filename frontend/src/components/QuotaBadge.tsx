import { useEffect } from "react";
import { useQuotaStore } from "@/store/quotaStore";
import { getQuotaStatus } from "@/lib/api";

const TIER_LABEL: Record<string, string> = {
  free: "免費",
  pro: "進階",
  unlimited: "無限",
  admin: "管理員",
};

const TIER_COLOR: Record<string, string> = {
  free: "rgba(148,163,184,0.2)",
  pro: "var(--accent-soft)",
  unlimited: "rgba(34,197,94,0.25)",
  admin: "rgba(244,114,182,0.25)",
};

function formatReset(iso: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-TW", {
      hour: "2-digit",
      minute: "2-digit",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return "";
  }
}

interface Props {
  loadOnMount?: boolean;
}

export function QuotaBadge({ loadOnMount = true }: Props) {
  const quota = useQuotaStore();

  useEffect(() => {
    if (!loadOnMount || quota.loaded) return;
    getQuotaStatus()
      .then((q) =>
        quota.setQuota({
          tier: q.tier,
          status: q.status,
          daily_limit: q.daily_limit,
          used_today: q.used_today,
          remaining: q.remaining,
          reset_at: q.reset_at,
        }),
      )
      .catch(() => {
        // silently fail; user might be unauthenticated or backend down
      });
  }, [loadOnMount, quota]);

  if (!quota.loaded) return null;

  const unlimited = quota.daily_limit === -1;
  const lowQuota = !unlimited && quota.daily_limit > 0 && quota.remaining <= 2;
  const tierLabel = TIER_LABEL[quota.tier] ?? quota.tier;
  const bg = TIER_COLOR[quota.tier] ?? "rgba(148,163,184,0.2)";

  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs text-ink-strong"
      style={{
        background: bg,
        border: "1px solid rgba(255,255,255,0.08)",
      }}
      title={`重置時間：${formatReset(quota.reset_at)}`}
    >
      <span className="font-semibold">{tierLabel}</span>
      <span className="text-ink-secondary">·</span>
      {unlimited ? (
        <span className="text-emerald-300">無限額度</span>
      ) : (
        <span className={lowQuota ? "text-amber-300 font-semibold" : ""}>
          {quota.used_today}/{quota.daily_limit}
        </span>
      )}
    </div>
  );
}
