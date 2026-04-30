import { create } from "zustand";

export interface QuotaState {
  tier: string;
  status: string;
  daily_limit: number; // -1 = unlimited
  used_today: number;
  remaining: number; // -1 = unlimited
  reset_at: string; // ISO datetime
  loaded: boolean;
  exhausted: boolean;
  exhaustedReason: string | null;
  exhaustedMessage: string | null;
}

interface QuotaActions {
  setQuota: (q: Partial<QuotaState>) => void;
  setExhausted: (reason: string, message: string, resetAt?: string) => void;
  clearExhausted: () => void;
  applyHeaders: (headers: Headers) => void;
}

const initial: QuotaState = {
  tier: "free",
  status: "active",
  daily_limit: 0,
  used_today: 0,
  remaining: 0,
  reset_at: "",
  loaded: false,
  exhausted: false,
  exhaustedReason: null,
  exhaustedMessage: null,
};

export const useQuotaStore = create<QuotaState & QuotaActions>((set) => ({
  ...initial,
  setQuota: (q) => set((s) => ({ ...s, ...q, loaded: true })),
  setExhausted: (reason, message, resetAt) =>
    set((s) => ({
      ...s,
      exhausted: true,
      exhaustedReason: reason,
      exhaustedMessage: message,
      reset_at: resetAt || s.reset_at,
      remaining: 0,
    })),
  clearExhausted: () =>
    set((s) => ({
      ...s,
      exhausted: false,
      exhaustedReason: null,
      exhaustedMessage: null,
    })),
  applyHeaders: (headers) => {
    const tier = headers.get("X-Quota-Tier");
    if (!tier) return;
    const dl = headers.get("X-Quota-Daily-Limit");
    const used = headers.get("X-Quota-Used");
    const remaining = headers.get("X-Quota-Remaining");
    const reset = headers.get("X-Quota-Reset");
    set((s) => ({
      ...s,
      tier,
      daily_limit: dl ? Number(dl) : s.daily_limit,
      used_today: used ? Number(used) : s.used_today,
      remaining: remaining ? Number(remaining) : s.remaining,
      reset_at: reset || s.reset_at,
      loaded: true,
    }));
  },
}));
