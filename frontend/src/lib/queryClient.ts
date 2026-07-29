import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";

/**
 * 全站共用的 QueryClient。
 *
 * 預設值的取捨：
 * - `staleTime` 60 秒只是保底，各 query 依後端 TTL 自行覆寫（見 lib/queries/stock.ts）。
 *   後端本來就是 TTL 快取（台股報價 30 分鐘、新聞 30 分鐘），前端訂得比它短，
 *   代表「快取命中時看到的資料，不會比重打一次 API 拿到的更舊」。
 * - `gcTime` 30 分鐘：決定「離開頁面多久內回來還算快取命中」。預設 5 分鐘對
 *   看盤這種來回切換的操作太短，同一檔股票查完切走再回來就又要重打。
 * - `retry` 只重試伺服器端錯誤。404（查無此股票）、403（沒權限）重試三次
 *   只是讓使用者多等好幾秒，答案不會變。
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 30 * 60_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});
