import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getFeatureAccess } from "@/lib/api";

/**
 * 帳號層級資料（功能權限）的 React Query 層。
 *
 * 功能權限原本被三個地方各自抓一次：Layout 的側邊選單、Dashboard 的功能卡片、
 * 以及包住 stock/portfolio/screener 三條路由的 FeatureGuard。等於每導覽一次
 * 就重打一次同一支 API，FeatureGuard 還會整頁擋在「檢查功能權限中…」。
 * 收斂成同一個 queryKey 後，三處共用一份快取，導覽不再重打也不再閃。
 *
 * 這層快取不影響安全性：後端每支 API 都有 `require_feature_access` 把關，
 * 前端這份只決定要不要把入口畫出來。
 */

const MINUTE = 60_000;

export const accountKeys = {
  all: ["account"] as const,
  featureAccess: () => ["account", "feature-access"] as const,
};

export function useFeatureAccess() {
  return useQuery({
    queryKey: accountKeys.featureAccess(),
    queryFn: getFeatureAccess,
    staleTime: 5 * MINUTE,
  });
}

/**
 * 已開放的 feature key 集合，給選單與卡片做顯示過濾用。
 *
 * 回 `null` 代表「還沒拿到權限資料」——載入中與抓取失敗都算，
 * 呼叫端一律當作不套用限制（維持遷移前的 fail-open 行為：
 * 寧可多顯示一個入口讓後端擋下，也不要因為權限查不到就把選單清空）。
 */
export function useAllowedFeatures(): Set<string> | null {
  const { data } = useFeatureAccess();
  return useMemo(() => {
    if (!data) return null;
    return new Set(
      data.features.filter((f) => f.allowed).map((f) => f.feature_key),
    );
  }, [data]);
}
