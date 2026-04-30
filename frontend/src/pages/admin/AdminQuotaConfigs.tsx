import { useEffect, useState } from "react";
import { adminListQuotaConfigs, adminUpdateQuotaConfig } from "@/lib/api";
import type { QuotaConfig } from "@/lib/api";

export default function AdminQuotaConfigs() {
  const [configs, setConfigs] = useState<QuotaConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, Partial<QuotaConfig>>>({});
  const [savedTier, setSavedTier] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    adminListQuotaConfigs()
      .then((r) => setConfigs(r.configs))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const updateEdit = (tier: string, key: keyof QuotaConfig, value: string) => {
    setEdits((prev) => ({
      ...prev,
      [tier]: {
        ...prev[tier],
        [key]: key === "description" ? value : Number(value),
      },
    }));
  };

  const save = async (tier: string) => {
    const patch = edits[tier];
    if (!patch || Object.keys(patch).length === 0) return;
    try {
      await adminUpdateQuotaConfig(tier, patch);
      setSavedTier(tier);
      setEdits((p) => ({ ...p, [tier]: {} }));
      setTimeout(() => setSavedTier(null), 2500);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  if (loading) return <p className="text-sm text-slate-500">載入中…</p>;

  return (
    <div className="space-y-4 max-w-4xl">
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <p className="text-xs text-slate-600">
        調整每個 Tier 的每日訊息上限與每分鐘速率。<code>-1</code> 代表無限。
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {configs.map((c) => {
          const e = edits[c.tier] || {};
          const dirty = Object.keys(e).length > 0;
          const dailyVal = e.daily_limit ?? c.daily_limit;
          const minuteVal = e.per_minute_limit ?? c.per_minute_limit;
          const descVal = e.description ?? (c.description || "");
          return (
            <div
              key={c.tier}
              className="rounded-xl p-5"
              style={{
                background: "var(--card-bg)",
                border: "1px solid var(--border)",
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-slate-100 uppercase">
                  {c.tier}
                </h3>
                {savedTier === c.tier && (
                  <span className="text-[11px] text-emerald-400">已儲存</span>
                )}
              </div>
              <div className="space-y-3">
                <Row label="每日訊息上限">
                  <input
                    type="number"
                    value={dailyVal}
                    onChange={(ev) =>
                      updateEdit(c.tier, "daily_limit", ev.target.value)
                    }
                    className="w-full px-3 py-1.5 rounded-lg text-sm bg-transparent text-slate-200"
                    style={{ border: "1px solid var(--border)" }}
                  />
                </Row>
                <Row label="每分鐘上限">
                  <input
                    type="number"
                    value={minuteVal}
                    onChange={(ev) =>
                      updateEdit(c.tier, "per_minute_limit", ev.target.value)
                    }
                    className="w-full px-3 py-1.5 rounded-lg text-sm bg-transparent text-slate-200"
                    style={{ border: "1px solid var(--border)" }}
                  />
                </Row>
                <Row label="描述">
                  <input
                    value={descVal}
                    onChange={(ev) =>
                      updateEdit(c.tier, "description", ev.target.value)
                    }
                    className="w-full px-3 py-1.5 rounded-lg text-sm bg-transparent text-slate-200"
                    style={{ border: "1px solid var(--border)" }}
                  />
                </Row>
              </div>
              <button
                onClick={() => save(c.tier)}
                disabled={!dirty}
                className="mt-4 w-full px-3 py-2 rounded-lg text-xs text-white disabled:opacity-30"
                style={{
                  background: "linear-gradient(135deg,#6366f1,#8b5cf6)",
                }}
              >
                儲存
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[11px] text-slate-600 mb-1 block">{label}</span>
      {children}
    </label>
  );
}
