import { create } from "zustand";

interface PrivacyState {
  /** 損益/持股是否鎖定（遮住）。隱私優先：預設鎖定。 */
  pnlLocked: boolean;
  lock: () => void;
  unlock: () => void;
  toggleLock: () => void;
}

// 刻意不做 localStorage 持久化：每次重新載入頁面都回到「鎖定」，
// 符合「不要一進頁面就露出損益」的需求；SPA 內切換頁面時 store 仍存活，
// 已解鎖狀態會保留，直到使用者重新鎖定或整頁重新整理。
export const usePrivacyStore = create<PrivacyState>((set) => ({
  pnlLocked: true,
  lock: () => set({ pnlLocked: true }),
  unlock: () => set({ pnlLocked: false }),
  toggleLock: () => set((s) => ({ pnlLocked: !s.pnlLocked })),
}));
