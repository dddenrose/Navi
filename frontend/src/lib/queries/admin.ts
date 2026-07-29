import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  adminGetUsageSummary,
  adminGetUser,
  adminListFeatureAccessConfigs,
  adminListLogs,
  adminListQuotaConfigs,
  adminListUsers,
  adminUpdateFeatureAccessConfig,
  adminUpdateQuotaConfig,
  adminUpdateUser,
  type FeatureAccessConfig,
  type QuotaConfig,
} from "@/lib/api";
import { accountKeys } from "@/lib/queries/account";

/**
 * 後台資料的 React Query 層。
 *
 * 這裡的取捨和一般頁面不同：
 * - `refetchOnWindowFocus: false`。後台幾乎每頁都有「改到一半的表單」
 *   （quota 的 edits、使用者詳情的欄位），切出去接個訊息再切回來就被
 *   背景更新蓋掉編輯內容，是最惱人的那種 bug。
 * - staleTime 短（30 秒）。管理者要看的是現況，只求在頁籤之間來回切
 *   的那幾秒內不重打。真的要最新資料一律有「重新查詢」按鈕走 refetch()，
 *   refetch 不理會 staleTime，一定會打。
 */

const THIRTY_SECONDS = 30_000;

export interface AdminUserFilters {
  q?: string;
  tier?: string;
  status?: string;
}

export interface AdminLogFilters {
  uid?: string;
  blocked?: boolean;
}

export const adminKeys = {
  all: ["admin"] as const,
  usageSummary: (days: number) => ["admin", "usage-summary", days] as const,
  users: (filters: AdminUserFilters) => ["admin", "users", filters] as const,
  user: (uid: string) => ["admin", "user", uid] as const,
  quotaConfigs: () => ["admin", "quota-configs"] as const,
  featureAccessConfigs: () => ["admin", "feature-access-configs"] as const,
  logs: (filters: AdminLogFilters) => ["admin", "logs", filters] as const,
};

const adminDefaults = {
  staleTime: THIRTY_SECONDS,
  refetchOnWindowFocus: false,
} as const;

export function useAdminUsageSummary(days = 30) {
  return useQuery({
    queryKey: adminKeys.usageSummary(days),
    queryFn: () => adminGetUsageSummary(days),
    ...adminDefaults,
  });
}

export function useAdminUsers(filters: AdminUserFilters) {
  return useQuery({
    queryKey: adminKeys.users(filters),
    queryFn: () =>
      adminListUsers({
        q: filters.q || undefined,
        tier: filters.tier || undefined,
        status: filters.status || undefined,
        limit: 200,
      }),
    ...adminDefaults,
  });
}

export function useAdminUser(uid: string) {
  return useQuery({
    queryKey: adminKeys.user(uid),
    queryFn: () => adminGetUser(uid),
    enabled: Boolean(uid),
    ...adminDefaults,
  });
}

export function useAdminLogs(filters: AdminLogFilters) {
  return useQuery({
    queryKey: adminKeys.logs(filters),
    queryFn: () => adminListLogs({ ...filters, limit: 200 }),
    ...adminDefaults,
  });
}

export function useAdminQuotaConfigs() {
  return useQuery({
    queryKey: adminKeys.quotaConfigs(),
    queryFn: adminListQuotaConfigs,
    ...adminDefaults,
  });
}

export function useAdminFeatureAccessConfigs() {
  return useQuery({
    queryKey: adminKeys.featureAccessConfigs(),
    queryFn: adminListFeatureAccessConfigs,
    ...adminDefaults,
  });
}

/**
 * 更新使用者。成功後同時失效該使用者的詳情與所有使用者列表——
 * 列表的 queryKey 帶著篩選條件，用前綴 `["admin","users"]` 一次涵蓋所有組合，
 * 否則改完 tier 回到列表還是看到舊值。
 */
export function useAdminUpdateUser(uid: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: Parameters<typeof adminUpdateUser>[1]) =>
      adminUpdateUser(uid, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.user(uid) });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useAdminUpdateQuotaConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tier, patch }: { tier: string; patch: Partial<QuotaConfig> }) =>
      adminUpdateQuotaConfig(tier, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.quotaConfigs() });
    },
  });
}

/**
 * 更新功能開放設定。除了後台自己的列表，一併失效 `account/feature-access`：
 * 管理者改完權限後，自己的側邊選單與 FeatureGuard 就會跟著更新，
 * 不必重整頁面才看得到效果。
 */
export function useAdminUpdateFeatureAccessConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      featureKey,
      patch,
    }: {
      featureKey: string;
      patch: Partial<
        Pick<FeatureAccessConfig, "enabled" | "allowed_tiers" | "description">
      >;
    }) => adminUpdateFeatureAccessConfig(featureKey, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: adminKeys.featureAccessConfigs(),
      });
      queryClient.invalidateQueries({ queryKey: accountKeys.featureAccess() });
    },
  });
}
