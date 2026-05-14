import { useEffect, useState } from "react";
import {
  adminListFeatureAccessConfigs,
  adminUpdateFeatureAccessConfig,
} from "@/lib/api";
import type { FeatureAccessConfig } from "@/lib/api";

const TIERS = ["free", "pro", "unlimited", "admin"];

export default function AdminFeatureAccess() {
  const [configs, setConfigs] = useState<FeatureAccessConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminListFeatureAccessConfigs()
      .then((result) => {
        if (cancelled) return;
        setConfigs(result.configs);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(String(err));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyPatch = async (
    featureKey: string,
    patch: Partial<
      Pick<FeatureAccessConfig, "enabled" | "allowed_tiers" | "description">
    >,
  ) => {
    setSavingKey(featureKey);
    setSavedKey(null);
    setError(null);
    try {
      const result = await adminUpdateFeatureAccessConfig(featureKey, patch);
      setConfigs((current) =>
        current.map((config) =>
          config.feature_key === featureKey ? result.config : config,
        ),
      );
      setSavedKey(featureKey);
      setTimeout(() => setSavedKey(null), 2200);
    } catch (err) {
      setError(String(err));
    } finally {
      setSavingKey(null);
    }
  };

  const toggleTier = (config: FeatureAccessConfig, tier: string) => {
    const hasTier = config.allowed_tiers.includes(tier);
    const nextTiers = hasTier
      ? config.allowed_tiers.filter((item) => item !== tier)
      : [...config.allowed_tiers, tier];
    if (nextTiers.length === 0) {
      setError(
        "每個功能至少需要保留一個可使用的 Tier；若要全面關閉請切換啟用狀態。",
      );
      return;
    }
    void applyPatch(config.feature_key, { allowed_tiers: nextTiers });
  };

  if (loading) return <p className="text-sm text-slate-500">載入中…</p>;

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <h2 className="text-sm font-bold text-slate-100">功能權限</h2>
        <p className="mt-1 text-xs text-slate-600">
          設定各功能可使用的 Tier。後端 API 會同步套用，因此直接呼叫 endpoint
          也會被權限檢查擋下。
        </p>
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {configs.map((config) => {
          const saving = savingKey === config.feature_key;
          return (
            <section
              key={config.feature_key}
              className="rounded-xl p-5"
              style={{
                background: "var(--card-bg)",
                border: "1px solid var(--border)",
              }}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-100">
                      {config.display_name}
                    </h3>
                    <span className="rounded bg-white/5 px-2 py-0.5 text-[10px] font-mono text-slate-500">
                      {config.feature_key}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    {config.description}
                  </p>
                </div>

                <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-300">
                  <span>{config.enabled ? "啟用" : "停用"}</span>
                  <input
                    type="checkbox"
                    checked={config.enabled}
                    disabled={saving}
                    onChange={(event) =>
                      void applyPatch(config.feature_key, {
                        enabled: event.target.checked,
                      })
                    }
                    className="sr-only"
                  />
                  <span
                    className={`relative h-6 w-11 rounded-full transition-colors ${
                      config.enabled ? "bg-indigo-500/80" : "bg-slate-700"
                    }`}
                    aria-hidden="true"
                  >
                    <span
                      className={`absolute top-1 h-4 w-4 rounded-full bg-white transition-transform ${
                        config.enabled ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </span>
                </label>
              </div>

              <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-2">
                {TIERS.map((tier) => {
                  const checked = config.allowed_tiers.includes(tier);
                  return (
                    <label
                      key={tier}
                      className={`flex cursor-pointer items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                        checked
                          ? "text-white"
                          : "text-slate-500 hover:text-slate-300"
                      }`}
                      style={{
                        background: checked
                          ? "rgba(99,102,241,0.22)"
                          : "rgba(255,255,255,0.03)",
                        border: checked
                          ? "1px solid rgba(99,102,241,0.45)"
                          : "1px solid var(--border)",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={saving}
                        onChange={() => toggleTier(config, tier)}
                        className="h-3.5 w-3.5 rounded border-slate-600 bg-transparent accent-indigo-500"
                      />
                      <span className="uppercase">{tier}</span>
                    </label>
                  );
                })}
              </div>

              <div className="mt-4 flex items-center justify-between text-[11px]">
                <span className="text-slate-700">
                  {saving
                    ? "儲存中…"
                    : savedKey === config.feature_key
                      ? "已儲存"
                      : "自動儲存"}
                </span>
                <span className="text-slate-700">
                  {config.updated_by
                    ? `更新者：${config.updated_by}`
                    : "尚未寫入設定"}
                </span>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
