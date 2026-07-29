import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addHolding,
  addPortfolioTransaction,
  deleteHolding,
  estimateTransactionCosts,
  getPortfolio,
  getPortfolioTransactions,
  updateHolding,
  type AddTransactionInput,
} from "@/lib/api";

/**
 * 投資組合的 React Query 層。
 *
 * 這頁的資料會被自己的操作改動（新增／修改／刪除持股、記一筆交易），
 * 所以重點不只是快取，而是「改完之後誰該重抓」：四個 mutation 一律
 * 失效 `portfolio` 前綴底下的所有 query，取代原本每個 handler 手動
 * 呼叫一次 `fetchPortfolio()` 的寫法——少一個「忘記加」的破口。
 */

const MINUTE = 60_000;

export const portfolioKeys = {
  all: ["portfolio"] as const,
  summary: () => ["portfolio", "summary"] as const,
  transactions: () => ["portfolio", "transactions"] as const,
  estimate: (ticker: string, action: string, shares: number, price: number) =>
    ["portfolio", "estimate", ticker, action, shares, price] as const,
};

/** 持股總覽（含即時報價與損益）。報價會動，所以只快取 1 分鐘。 */
export function usePortfolio() {
  return useQuery({
    queryKey: portfolioKeys.summary(),
    queryFn: getPortfolio,
    staleTime: MINUTE,
  });
}

/** 交易紀錄。歷史資料，除非自己剛記一筆否則不會變。 */
export function usePortfolioTransactions() {
  return useQuery({
    queryKey: portfolioKeys.transactions(),
    queryFn: getPortfolioTransactions,
    staleTime: 5 * MINUTE,
  });
}

/**
 * 費稅試算。呼叫端要自己先做 debounce 再把值傳進來——
 * 這裡的 queryKey 綁的是「已定案的輸入」，不是每個按鍵。
 * 快取的附帶好處：把股數改來改去又改回去，同一組參數不會再打一次。
 */
export function useTransactionCostEstimate(params: {
  ticker: string;
  action: string;
  shares: number;
  price: number;
  enabled: boolean;
}) {
  const { ticker, action, shares, price, enabled } = params;
  return useQuery({
    queryKey: portfolioKeys.estimate(ticker, action, shares, price),
    queryFn: () => estimateTransactionCosts(ticker, action, shares, price),
    enabled,
    staleTime: 30 * MINUTE,
  });
}

/** 四個寫入操作共用的失效範圍：總覽與交易紀錄都可能被同一次操作改到。 */
function useInvalidatePortfolio() {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
}

export function useAddHolding() {
  const invalidate = useInvalidatePortfolio();
  return useMutation({
    mutationFn: (data: Parameters<typeof addHolding>[0]) => addHolding(data),
    onSuccess: invalidate,
  });
}

export function useAddTransaction() {
  const invalidate = useInvalidatePortfolio();
  return useMutation({
    mutationFn: (data: AddTransactionInput) => addPortfolioTransaction(data),
    onSuccess: invalidate,
  });
}

export function useUpdateHolding() {
  const invalidate = useInvalidatePortfolio();
  return useMutation({
    mutationFn: ({
      holdingId,
      data,
    }: {
      holdingId: string;
      data: Parameters<typeof updateHolding>[1];
    }) => updateHolding(holdingId, data),
    onSuccess: invalidate,
  });
}

export function useDeleteHolding() {
  const invalidate = useInvalidatePortfolio();
  return useMutation({
    mutationFn: (holdingId: string) => deleteHolding(holdingId),
    onSuccess: invalidate,
  });
}
