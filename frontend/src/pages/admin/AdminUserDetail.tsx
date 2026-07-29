import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { adminUpdateUser, AdminUser } from "@/lib/api";
import { useAdminUpdateUser, useAdminUser } from "@/lib/queries/admin";
import { TierBadge } from "./AdminUsers";

/** 後端的 null/undefined 與輸入框的空字串來回對應，兩處判斷要一致。 */
function customLimitToInput(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

export default function AdminUserDetail() {
  const { uid = "" } = useParams();
  const { data, error: loadError } = useAdminUser(uid);
  const updateUser = useAdminUpdateUser(uid);

  const [localError, setLocalError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  // Editable fields
  const [tier, setTier] = useState("");
  const [status, setStatus] = useState("");
  const [customLimit, setCustomLimit] = useState<string>("");
  const [notes, setNotes] = useState("");

  const user = data?.user ?? null;
  const usage = data?.usage ?? [];
  const error = localError ?? loadError ?? updateUser.error;
  const saving = updateUser.isPending;

  // 表單欄位以 server 資料為初值。React Query 的 data 物件在資料沒變時
  // 參照是穩定的，因此這個比對只會在「首次載入」與「存檔後重抓」時成立，
  // 不會在每次 render 把管理者正在編輯的內容洗掉。
  // （admin query 已關掉 refetchOnWindowFocus，切出去再回來也不會被蓋。）
  const [seededFrom, setSeededFrom] = useState<AdminUser | null>(null);
  if (user && user !== seededFrom) {
    setSeededFrom(user);
    setTier(user.tier);
    setStatus(user.status);
    setCustomLimit(customLimitToInput(user.custom_daily_limit));
    setNotes(user.notes || "");
  }

  const save = async () => {
    setLocalError(null);
    setSavedMsg(null);
    try {
      const patch: Parameters<typeof adminUpdateUser>[1] = {};
      if (tier !== user?.tier) patch.tier = tier;
      if (status !== user?.status) patch.status = status;
      if (notes !== (user?.notes || "")) patch.notes = notes;
      const trimmed = customLimit.trim();
      const currentCustom = customLimitToInput(user?.custom_daily_limit);
      if (trimmed !== currentCustom) {
        if (trimmed === "") {
          // Clear via separate flag in API
          await updateUser.mutateAsync({ ...patch, custom_daily_limit: null });
          setSavedMsg("已儲存");
          return;
        }
        const v = Number(trimmed);
        if (Number.isNaN(v)) {
          setLocalError("自訂額度必須是數字");
          return;
        }
        patch.custom_daily_limit = v;
      }
      if (Object.keys(patch).length === 0) {
        setSavedMsg("沒有變更");
        return;
      }
      // 存檔後由 mutation 的 onSuccess 失效此使用者與使用者列表，
      // 資料重抓後上面的 seed 比對會把表單刷成最新值
      await updateUser.mutateAsync(patch);
      setSavedMsg("已儲存。tier 變更需使用者重新登入才會生效。");
    } catch {
      // 錯誤由 updateUser.error 呈現
    }
  };

  if (error) return <p className="text-sm text-rose-400">{String(error)}</p>;
  if (!user) return <p className="text-sm text-slate-500">載入中…</p>;

  const maxUsage = Math.max(1, ...usage.map((u) => u.chat_count));

  return (
    <div className="space-y-6 max-w-4xl">
      <Link
        to="/admin/users"
        className="text-xs text-indigo-400 hover:text-indigo-300"
      >
        ← 回使用者列表
      </Link>

      <div
        className="rounded-xl p-5"
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              {user.email || "(無 email)"}
            </h2>
            <p className="text-xs font-mono text-slate-600 mt-1">{user.uid}</p>
          </div>
          <TierBadge tier={user.tier} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Tier">
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm bg-transparent text-slate-200"
              style={{ border: "1px solid var(--border)" }}
            >
              {["free", "pro", "unlimited", "admin"].map((t) => (
                <option key={t} value={t} style={{ background: "#0f172a" }}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="狀態">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm bg-transparent text-slate-200"
              style={{ border: "1px solid var(--border)" }}
            >
              <option value="active" style={{ background: "#0f172a" }}>
                active
              </option>
              <option value="suspended" style={{ background: "#0f172a" }}>
                suspended
              </option>
            </select>
          </Field>
          <Field label="自訂每日額度（空白 = 用 tier 預設；-1 = 無限）">
            <input
              value={customLimit}
              onChange={(e) => setCustomLimit(e.target.value)}
              placeholder="（空白）"
              className="w-full px-3 py-2 rounded-lg text-sm bg-transparent text-slate-200"
              style={{ border: "1px solid var(--border)" }}
            />
          </Field>
          <Field label="備註">
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm bg-transparent text-slate-200"
              style={{ border: "1px solid var(--border)" }}
            />
          </Field>
        </div>

        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50"
            style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}
          >
            {saving ? "儲存中…" : "儲存變更"}
          </button>
          {savedMsg && (
            <span className="text-xs text-emerald-400">{savedMsg}</span>
          )}
          {error && <span className="text-xs text-rose-400">{error}</span>}
        </div>
      </div>

      <div
        className="rounded-xl p-5"
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
        }}
      >
        <h3 className="text-sm font-semibold text-slate-200 mb-3">
          近 30 天用量
        </h3>
        <div className="flex items-end gap-1 h-24">
          {usage
            .slice()
            .reverse()
            .map((d) => (
              <div
                key={d.date}
                className="flex-1 flex flex-col justify-end"
                title={`${d.date}: ${d.chat_count}`}
              >
                <div
                  className="w-full rounded-t"
                  style={{
                    height: `${(d.chat_count / maxUsage) * 100}%`,
                    background:
                      "linear-gradient(180deg, rgba(99,102,241,0.9), rgba(139,92,246,0.5))",
                    minHeight: d.chat_count > 0 ? "3px" : "1px",
                  }}
                />
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[11px] text-slate-600 mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}
