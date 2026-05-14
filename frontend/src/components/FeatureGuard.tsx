import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getFeatureAccess } from "@/lib/api";
import type { FeatureAccessItem } from "@/lib/api";

interface FeatureGuardProps {
  featureKey: string;
  featureName: string;
  children: ReactNode;
}

type AccessState =
  | { status: "loading" }
  | { status: "allowed" }
  | { status: "denied"; feature: FeatureAccessItem | null; tier: string }
  | { status: "error"; message: string };

export default function FeatureGuard({
  featureKey,
  featureName,
  children,
}: FeatureGuardProps) {
  const [state, setState] = useState<AccessState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getFeatureAccess()
      .then((data) => {
        if (cancelled) return;
        const feature = data.features.find(
          (item) => item.feature_key === featureKey,
        );
        if (feature?.allowed) {
          setState({ status: "allowed" });
          return;
        }
        setState({
          status: "denied",
          feature: feature ?? null,
          tier: data.tier,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({ status: "error", message: String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [featureKey]);

  if (state.status === "loading") {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <p className="text-sm text-slate-500">檢查功能權限中…</p>
      </div>
    );
  }

  if (state.status === "allowed") {
    return <>{children}</>;
  }

  if (state.status === "error") {
    return (
      <AccessPanel
        title="暫時無法確認權限"
        message={state.message}
        actionLabel="回到總覽"
      />
    );
  }

  const allowedTiers = state.feature?.allowed_tiers.join(" / ") || "管理員設定";
  const message =
    state.feature?.enabled === false
      ? `${featureName} 目前已被管理員停用。`
      : `目前帳號 Tier：${state.tier}。此功能開放給 ${allowedTiers}。`;

  return (
    <AccessPanel
      title={`${featureName} 尚未開放`}
      message={message}
      actionLabel="回到總覽"
    />
  );
}

function AccessPanel({
  title,
  message,
  actionLabel,
}: {
  title: string;
  message: string;
  actionLabel: string;
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
