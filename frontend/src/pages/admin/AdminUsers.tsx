import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminListUsers } from "@/lib/api";
import type { AdminUser } from "@/lib/api";

const TIERS = ["", "free", "pro", "unlimited", "admin"];
const STATUSES = ["", "active", "suspended"];

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [q, setQ] = useState("");
  const [tier, setTier] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    adminListUsers({
      q: q || undefined,
      tier: tier || undefined,
      status: status || undefined,
      limit: 200,
    })
      .then((r) => setUsers(r.users))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋 email…"
          className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-slate-200 placeholder-slate-700 focus:outline-none"
          style={{ border: "1px solid var(--border)" }}
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
        <button
          onClick={load}
          className="px-3 py-1.5 rounded-lg text-xs text-white"
          style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}
        >
          搜尋
        </button>
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
        }}
      >
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-600 text-left">
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
                  className="px-4 py-6 text-center text-slate-600"
                  colSpan={6}
                >
                  載入中…
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td
                  className="px-4 py-6 text-center text-slate-600"
                  colSpan={6}
                >
                  無資料
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.uid} className="border-t border-white/5">
                  <td className="px-4 py-3 text-slate-200">{u.email || "—"}</td>
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
                  <td className="px-4 py-3 text-slate-300">
                    {u.custom_daily_limit === null ||
                    u.custom_daily_limit === undefined
                      ? "—"
                      : u.custom_daily_limit === -1
                        ? "∞"
                        : u.custom_daily_limit}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {u.last_active_at
                      ? new Date(u.last_active_at).toLocaleDateString("zh-TW")
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/admin/users/${u.uid}`}
                      className="text-indigo-400 hover:text-indigo-300"
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
      className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-slate-200 focus:outline-none"
      style={{ border: "1px solid var(--border)" }}
    >
      {options.map((o) => (
        <option key={o} value={o} style={{ background: "#0f172a" }}>
          {o || placeholder}
        </option>
      ))}
    </select>
  );
}

export function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    free: "rgba(148,163,184,0.25)",
    pro: "rgba(99,102,241,0.3)",
    unlimited: "rgba(34,197,94,0.3)",
    admin: "rgba(244,114,182,0.3)",
  };
  return (
    <span
      className="px-2 py-0.5 rounded text-[10px] font-semibold text-slate-100"
      style={{ background: colors[tier] || "rgba(148,163,184,0.2)" }}
    >
      {tier}
    </span>
  );
}
