import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useFeatureAccess } from "@/lib/queries/account";

interface FeatureGuardProps {
  featureKey: string;
  featureName: string;
  children: ReactNode;
}

export default function FeatureGuard({
  featureKey,
  featureName,
  children,
}: FeatureGuardProps) {
  // 權限清單與 Layout、Dashboard 共用快取：導覽回到已檢查過的功能時
  // isPending 直接是 false，不會再擋一次「檢查功能權限中…」。
  const { data, isPending, isError } = useFeatureAccess();

  if (isPending) {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <p className="text-sm text-slate-500">檢查功能權限中…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <AccessPanel
        title="暫時無法確認權限"
        message="無法確認你的功能權限，請稍後重試。"
        actionLabel="回到總覽"
      />
    );
  }

  const feature =
    data.features.find((item) => item.feature_key === featureKey) ?? null;

  if (feature?.allowed) {
    return <>{children}</>;
  }

  const allowedTiers = feature?.allowed_tiers.join(" / ") || "管理員設定";
  const isDisabled = feature?.enabled === false;
  const message = isDisabled
    ? `${featureName} 目前已被管理員停用。`
    : `目前帳號方案：${data.tier}。此功能開放給 ${allowedTiers} 方案。`;

  return (
    <AccessPanel
      title={`${featureName} 尚未開放`}
      message={message}
      actionLabel="回到總覽"
      upgradeHint={
        !isDisabled
          ? "想使用此功能？升級方案即可解鎖進階分析工具（升級方式請洽管理員或關注公告）。"
          : undefined
      }
    />
  );
}

function AccessPanel({
  title,
  message,
  actionLabel,
  upgradeHint,
}: {
  title: string;
  message: string;
  actionLabel: string;
  upgradeHint?: string;
}) {
  return (
    <div className="flex items-center justify-center h-full min-h-[60vh] px-4">
      <div
        className="w-full max-w-md rounded-xl p-6 text-center"
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
        }}
      >
        <div
          className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl text-slate-100"
          style={{ background: "rgba(99,102,241,0.18)" }}
          aria-hidden="true"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
            <path
              fillRule="evenodd"
              d="M10 1a4.5 4.5 0 00-4.5 4.5V8H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 7V5.5a3 3 0 10-6 0V8h6z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <h2 className="text-base font-bold text-slate-100">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">{message}</p>
        {upgradeHint && (
          <p
            className="mt-3 rounded-lg px-3 py-2 text-xs leading-5 text-indigo-300"
            style={{
              background: "rgba(99,102,241,0.08)",
              border: "1px solid rgba(99,102,241,0.2)",
            }}
          >
            {upgradeHint}
          </p>
        )}
        <Link
          to="/dashboard"
          className="mt-5 inline-flex items-center justify-center rounded-lg px-4 py-2 text-xs font-medium text-white"
          style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}
        >
          {actionLabel}
        </Link>
      </div>
    </div>
  );
}
