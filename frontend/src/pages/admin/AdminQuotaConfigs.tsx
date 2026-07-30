import { useState } from "react";
import {
  useAdminQuotaConfigs,
  useAdminUpdateQuotaConfig,
} from "@/lib/queries/admin";
import type { QuotaConfig } from "@/lib/api";

export default function AdminQuotaConfigs() {
  const { data, isPending, error: loadError } = useAdminQuotaConfigs();
  const updateConfig = useAdminUpdateQuotaConfig();

  const [edits, setEdits] = useState<Record<string, Partial<QuotaConfig>>>({});
  const [savedTier, setSavedTier] = useState<string | null>(null);

  const configs = data?.configs ?? [];
  const error = loadError ?? updateConfig.error;

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
      // mutation 成功後由 onSuccess 失效 quota-configs，列表自動重抓，
      // 不需要再手動 load()
      await updateConfig.mutateAsync({ tier, patch });
      setSavedTier(tier);
      setEdits((p) => ({ ...p, [tier]: {} }));
      setTimeout(() => setSavedTier(null), 2500);
    } catch {
      // 錯誤已由 updateConfig.error 帶出，此處僅避免未捕捉的 rejection
    }
  };

  if (isPending) return <p className="text-sm text-ink-muted">載入中…</p>;

  return (
    <div className="space-y-4 max-w-4xl">
      {error && <p className="text-xs text-rose-400">{String(error)}</p>}
      <p className="text-xs text-ink-faint">
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
            <div key={c.tier} className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-ink-strong uppercase">
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
                    className="w-full px-3 py-1.5 rounded-lg text-sm bg-transparent text-ink border border-line-subtle"
                  />
                </Row>
                <Row label="每分鐘上限">
                  <input
                    type="number"
                    value={minuteVal}
                    onChange={(ev) =>
                      updateEdit(c.tier, "per_minute_limit", ev.target.value)
                    }
                    className="w-full px-3 py-1.5 rounded-lg text-sm bg-transparent text-ink border border-line-subtle"
                  />
                </Row>
                <Row label="描述">
                  <input
                    value={descVal}
                    onChange={(ev) =>
                      updateEdit(c.tier, "description", ev.target.value)
                    }
                    className="w-full px-3 py-1.5 rounded-lg text-sm bg-transparent text-ink border border-line-subtle"
                  />
                </Row>
              </div>
              <button
                onClick={() => save(c.tier)}
                disabled={!dirty}
                className="btn btn-primary rounded-lg mt-4 w-full px-3 py-2 text-xs disabled:opacity-30"
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
      <span className="text-[11px] text-ink-faint mb-1 block">{label}</span>
      {children}
    </label>
  );
}
