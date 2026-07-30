import { useState } from "react";
import { useAdminLogs, type AdminLogFilters } from "@/lib/queries/admin";

const EMPTY_FILTERS: AdminLogFilters = {};

export default function AdminLogs() {
  const [uid, setUid] = useState("");
  const [blocked, setBlocked] = useState<"" | "true" | "false">("");
  // 篩選條件改變不會自動查；一律由「重新查詢」按鈕觸發（維持原行為）
  const [filters, setFilters] = useState<AdminLogFilters>(EMPTY_FILTERS);

  const { data, isFetching, error, refetch } = useAdminLogs(filters);
  const logs = data?.logs ?? [];
  const loading = isFetching;

  const search = () => {
    const next: AdminLogFilters = {
      uid: uid || undefined,
      blocked: blocked === "" ? undefined : blocked === "true",
    };
    const changed =
      next.uid !== filters.uid || next.blocked !== filters.blocked;
    if (changed) setFilters(next);
    else refetch();
  };

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={uid}
          onChange={(e) => setUid(e.target.value)}
          placeholder="Filter by UID…"
          className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-ink placeholder:text-ink-faint border border-line-subtle focus:outline-none"
        />
        <select
          value={blocked}
          onChange={(e) => setBlocked(e.target.value as "" | "true" | "false")}
          className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-ink border border-line-subtle focus:outline-none"
        >
          <option value="" style={{ background: "var(--bg-surface)" }}>
            全部
          </option>
          <option value="false" style={{ background: "var(--bg-surface)" }}>
            已通過
          </option>
          <option value="true" style={{ background: "var(--bg-surface)" }}>
            已被擋
          </option>
        </select>
        <button
          onClick={search}
          className="btn btn-primary rounded-lg px-3 py-1.5 text-xs"
        >
          重新查詢
        </button>
      </div>

      {error && <p className="text-xs text-rose-400">{String(error)}</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ink-faint text-left">
              <th className="px-4 py-3">時間</th>
              <th className="px-4 py-3">Email / UID</th>
              <th className="px-4 py-3">Tier</th>
              <th className="px-4 py-3">問題</th>
              <th className="px-4 py-3">狀態</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td
                  className="px-4 py-6 text-center text-ink-faint"
                  colSpan={5}
                >
                  載入中…
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td
                  className="px-4 py-6 text-center text-ink-faint"
                  colSpan={5}
                >
                  無資料
                </td>
              </tr>
            ) : (
              logs.map((l) => (
                <tr key={l.id} className="border-t border-line-subtle">
                  <td className="px-4 py-3 text-ink-muted whitespace-nowrap">
                    {l.timestamp
                      ? new Date(l.timestamp).toLocaleString("zh-TW")
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-ink">{l.email || "—"}</div>
                    <div className="text-[10px] font-mono text-ink-faint">
                      {l.uid}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-ink">{l.tier}</td>
                  <td className="px-4 py-3 text-ink-secondary max-w-md truncate">
                    {l.question_preview || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {l.blocked ? (
                      <span className="text-rose-400">
                        擋下：{l.block_reason || ""}
                      </span>
                    ) : (
                      <span className="text-emerald-400">通過</span>
                    )}
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
