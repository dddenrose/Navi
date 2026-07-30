import { useState } from "react";
import {
  useAdminFeatureAccessConfigs,
  useAdminUpdateFeatureAccessConfig,
} from "@/lib/queries/admin";
import type { FeatureAccessConfig } from "@/lib/api";

const TIERS = ["free", "pro", "unlimited", "admin"];

export default function AdminFeatureAccess() {
  const { data, isPending, error: loadError } = useAdminFeatureAccessConfigs();
  const updateConfig = useAdminUpdateFeatureAccessConfig();

  // 送出前就擋下的規則錯誤，與 API 回來的錯誤分開存：
  // 後者由 mutation 自己帶著，前者沒有對應的請求可掛。
  const [validationError, setValidationError] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);

  const configs = data?.configs ?? [];
  const error = validationError ?? loadError ?? updateConfig.error;
  // 只有正在送出的那一列要顯示儲存中
  const savingKey = updateConfig.isPending
    ? (updateConfig.variables?.featureKey ?? null)
    : null;

  const applyPatch = async (
    featureKey: string,
    patch: Partial<
      Pick<FeatureAccessConfig, "enabled" | "allowed_tiers" | "description">
    >,
  ) => {
    setSavedKey(null);
    setValidationError(null);
    try {
      await updateConfig.mutateAsync({ featureKey, patch });
      setSavedKey(featureKey);
      setTimeout(() => setSavedKey(null), 2200);
    } catch {
      // 錯誤由 updateConfig.error 呈現
    }
  };

  const toggleTier = (config: FeatureAccessConfig, tier: string) => {
    const hasTier = config.allowed_tiers.includes(tier);
    const nextTiers = hasTier
      ? config.allowed_tiers.filter((item) => item !== tier)
      : [...config.allowed_tiers, tier];
    if (nextTiers.length === 0) {
      setValidationError(
        "每個功能至少需要保留一個可使用的 Tier；若要全面關閉請切換啟用狀態。",
      );
      return;
    }
    void applyPatch(config.feature_key, { allowed_tiers: nextTiers });
  };

  if (isPending) return <p className="text-sm text-ink-muted">載入中…</p>;

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <h2 className="text-sm font-bold text-ink-strong">功能權限</h2>
        <p className="mt-1 text-xs text-ink-faint">
          設定各功能可使用的 Tier。後端 API 會同步套用，因此直接呼叫 endpoint
          也會被權限檢查擋下。
        </p>
      </div>

      {error && <p className="text-xs text-rose-400">{String(error)}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {configs.map((config) => {
          const saving = savingKey === config.feature_key;
          return (
            <section key={config.feature_key} className="card p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-ink-strong">
                      {config.display_name}
                    </h3>
                    <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-mono text-ink-muted">
                      {config.feature_key}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-ink-faint">
                    {config.description}
                  </p>
                </div>

                <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-ink">
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
                      config.enabled
                        ? "bg-[var(--accent-strong)]"
                        : "bg-[var(--surface-3)]"
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
                      className={`flex cursor-pointer items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors border ${
                        checked
                          ? "text-ink-strong bg-[var(--accent-soft)] border-transparent"
                          : "text-ink-muted hover:text-ink bg-[var(--surface-1)] border-line-subtle"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={saving}
                        onChange={() => toggleTier(config, tier)}
                        className="h-3.5 w-3.5 rounded border-line bg-transparent accent-[var(--accent-strong)]"
                      />
                      <span className="uppercase">{tier}</span>
                    </label>
                  );
                })}
              </div>

              <div className="mt-4 flex items-center justify-between text-[11px]">
                <span className="text-ink-faint">
                  {saving
                    ? "儲存中…"
                    : savedKey === config.feature_key
                      ? "已儲存"
                      : "自動儲存"}
                </span>
                <span className="text-ink-faint">
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
