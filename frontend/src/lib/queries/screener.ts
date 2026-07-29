import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getReport,
  getSubscription,
  getTrackingSummary,
  listReports,
  updateSubscription,
} from "@/lib/api/screener";
import type {
  EmailSubscription,
  ScreenerFrequency,
  ScreenerProfile,
} from "@/types/screener";

/**
 * 選股報告的 React Query 層。
 *
 * 這頁的操作特徵是「在幾個 profile／frequency 之間來回比較」，
 * 而報告是每日或每週產一次的靜態產物——同一份報告在一次瀏覽期間
 * 絕不會變。因此 staleTime 訂得比其他頁長很多，來回切換等同零成本。
 */

const MINUTE = 60_000;

export const screenerKeys = {
  all: ["screener"] as const,
  reports: (profile: ScreenerProfile, frequency: ScreenerFrequency) =>
    ["screener", "reports", profile, frequency] as const,
  report: (reportId: string) => ["screener", "report", reportId] as const,
  tracking: (profile: ScreenerProfile) =>
    ["screener", "tracking", profile] as const,
  subscription: () => ["screener", "subscription"] as const,
};

export function useScreenerReports(
  profile: ScreenerProfile,
  frequency: ScreenerFrequency,
) {
  return useQuery({
    queryKey: screenerKeys.reports(profile, frequency),
    queryFn: () => listReports({ profile, frequency, limit: 24 }),
    staleTime: 30 * MINUTE,
  });
}

/** 單份報告內容。產出後就不再變動，快取整個 session 都算新鮮。 */
export function useScreenerReport(reportId: string | null) {
  return useQuery({
    queryKey: screenerKeys.report(reportId ?? ""),
    queryFn: () => getReport(reportId as string),
    enabled: Boolean(reportId),
    staleTime: 60 * MINUTE,
  });
}

/** 推薦實績追蹤。`getTrackingSummary` 內部已把 404 轉成 null（尚無統計）。 */
export function useTrackingSummary(profile: ScreenerProfile) {
  return useQuery({
    queryKey: screenerKeys.tracking(profile),
    queryFn: () => getTrackingSummary(profile),
    staleTime: 30 * MINUTE,
  });
}

/**
 * Email 訂閱設定。查不到訂閱記錄時後端回錯誤，原本的頁面是靜默吞掉並套用
 * 預設值（未訂閱），所以這裡也把錯誤轉成 null，維持同樣的語意。
 */
export function useScreenerSubscription() {
  return useQuery({
    queryKey: screenerKeys.subscription(),
    queryFn: () => getSubscription().catch(() => null),
    staleTime: 5 * MINUTE,
  });
}

export function useUpdateScreenerSubscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      payload: Partial<Omit<EmailSubscription, "user_id" | "updated_at">>,
    ) => updateSubscription(payload),
    onSuccess: (updated) => {
      // 後端回傳更新後的完整設定，直接寫回快取即可，不必再打一次
      queryClient.setQueryData(screenerKeys.subscription(), updated);
    },
  });
}
