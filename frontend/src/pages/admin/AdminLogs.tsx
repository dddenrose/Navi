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
          className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-slate-200 placeholder-slate-700 focus:outline-none"
          style={{ border: "1px solid var(--border)" }}
        />
        <select
          value={blocked}
          onChange={(e) => setBlocked(e.target.value as "" | "true" | "false")}
          className="px-3 py-1.5 rounded-lg text-xs bg-transparent text-slate-200 focus:outline-none"
          style={{ border: "1px solid var(--border)" }}
        >
          <option value="" style={{ background: "#0f172a" }}>
            全部
          </option>
          <option value="false" style={{ background: "#0f172a" }}>
            已通過
          </option>
          <option value="true" style={{ background: "#0f172a" }}>
            已被擋
          </option>
        </select>
        <button
          onClick={search}
          className="px-3 py-1.5 rounded-lg text-xs text-white"
          style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}
        >
          重新查詢
        </button>
      </div>

      {error && <p className="text-xs text-rose-400">{String(error)}</p>}

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
                  className="px-4 py-6 text-center text-slate-600"
                  colSpan={5}
                >
                  載入中…
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td
                  className="px-4 py-6 text-center text-slate-600"
                  colSpan={5}
                >
                  無資料
                </td>
              </tr>
            ) : (
              logs.map((l) => (
                <tr key={l.id} className="border-t border-white/5">
                  <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                    {l.timestamp
                      ? new Date(l.timestamp).toLocaleString("zh-TW")
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-slate-200">{l.email || "—"}</div>
                    <div className="text-[10px] font-mono text-slate-700">
                      {l.uid}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{l.tier}</td>
                  <td className="px-4 py-3 text-slate-400 max-w-md truncate">
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
