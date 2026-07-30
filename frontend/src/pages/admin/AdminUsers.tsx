import { useState } from "react";
import { Link } from "react-router-dom";
import { useAdminUsers, type AdminUserFilters } from "@/lib/queries/admin";

const TIERS = ["", "free", "pro", "unlimited", "admin"];
const STATUSES = ["", "active", "suspended"];

const EMPTY_FILTERS: AdminUserFilters = { q: "", tier: "", status: "" };

export default function AdminUsers() {
  // 輸入框的即時值與「已送出的查詢條件」分開：queryKey 只綁後者，
  // 否則每打一個字都會變成一次新查詢（原本是按下搜尋才查）。
  const [q, setQ] = useState("");
  const [tier, setTier] = useState("");
  const [status, setStatus] = useState("");
  const [filters, setFilters] = useState<AdminUserFilters>(EMPTY_FILTERS);

  const { data, isFetching, error, refetch } = useAdminUsers(filters);
  const users = data?.users ?? [];
  const loading = isFetching;

  const load = () => {
    const next: AdminUserFilters = { q, tier, status };
    const changed =
      next.q !== filters.q ||
      next.tier !== filters.tier ||
      next.status !== filters.status;
    // 條件沒變時 queryKey 也不會變，要靠 refetch 才會真的重打——
    // 使用者按下「搜尋」的預期是「現在就去拿一次」，不是「看情況」。
    if (changed) setFilters(next);
    else refetch();
  };

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋 email…"
          className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-ink placeholder:text-ink-faint border border-line-subtle focus:outline-none"
        />
        <Select
          value={tier}
          onChange={setTier}
          options={TIERS}
          placeholder="全部 Tier"
        />
        <Select
          value={status}
          onChange={setStatus}
          options={STATUSES}
          placeholder="全部狀態"
        />
        <button onClick={load} className="btn btn-primary rounded-lg px-3 py-1.5 text-xs">
          搜尋
        </button>
      </div>

      {error && <p className="text-xs text-rose-400">{String(error)}</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ink-faint text-left">
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Tier</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">自訂額度</th>
              <th className="px-4 py-3">最後活動</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td
                  className="px-4 py-6 text-center text-ink-faint"
                  colSpan={6}
                >
                  載入中…
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td
                  className="px-4 py-6 text-center text-ink-faint"
                  colSpan={6}
                >
                  無資料
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.uid} className="border-t border-line-subtle">
                  <td className="px-4 py-3 text-ink">{u.email || "—"}</td>
                  <td className="px-4 py-3">
                    <TierBadge tier={u.tier} />
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        u.status === "suspended"
                          ? "text-rose-400"
                          : "text-emerald-400"
                      }
                    >
                      {u.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink">
                    {u.custom_daily_limit === null ||
                    u.custom_daily_limit === undefined
                      ? "—"
                      : u.custom_daily_limit === -1
                        ? "∞"
                        : u.custom_daily_limit}
                  </td>
                  <td className="px-4 py-3 text-ink-muted">
                    {u.last_active_at
                      ? new Date(u.last_active_at).toLocaleDateString("zh-TW")
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/admin/users/${u.uid}`}
                      className="text-accent hover:text-[var(--accent-strong)]"
                    >
                      編輯 →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-ink border border-line-subtle focus:outline-none"
    >
      {options.map((o) => (
        <option key={o} value={o} style={{ background: "var(--bg-surface)" }}>
          {o || placeholder}
        </option>
      ))}
    </select>
  );
}

export function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    free: "rgba(148,163,184,0.25)",
    pro: "var(--accent-soft)",
    unlimited: "rgba(34,197,94,0.3)",
    admin: "rgba(244,114,182,0.3)",
  };
  return (
    <span
      className="px-2 py-0.5 rounded text-[10px] font-semibold text-ink-strong"
      style={{ background: colors[tier] || "rgba(148,163,184,0.2)" }}
    >
      {tier}
    </span>
  );
}
