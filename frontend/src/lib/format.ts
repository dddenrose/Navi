// Shared number / display formatting utilities

const numFmt = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a number to 2 decimal places, returns "-" for null/undefined */
export const fmtNum = (n?: number | null): string =>
  n != null ? numFmt.format(n) : "-";

/** Format a decimal ratio as percentage (0.15 → "15.00%") */
export const fmtPct = (n?: number | null): string =>
  n != null ? `${numFmt.format(n * 100)}%` : "-";

/** Format a price with currency prefix */
export const fmtPrice = (
  n: number | null | undefined,
  currency: string,
): string => {
  if (n == null) return "-";
  const prefix = currency === "TWD" ? "NT$ " : "$";
  return `${prefix}${numFmt.format(n)}`;
};

/** Format a large number with T/B/M suffix */
export const fmtLarge = (n?: number | null, currency = ""): string => {
  if (n == null) return "-";
  const prefix = currency === "TWD" ? "NT$ " : "$";
  if (n >= 1e12) return `${prefix}${numFmt.format(n / 1e12)}T`;
  if (n >= 1e9) return `${prefix}${numFmt.format(n / 1e9)}B`;
  if (n >= 1e6) return `${prefix}${numFmt.format(n / 1e6)}M`;
  return `${prefix}${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n)}`;
};

/** Format a number with configurable decimal places using locale */
export function fmt(n: number, decimals = 0): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Tailwind text color class for P&L values */
export function pnlColor(n: number): string {
  if (n > 0) return "text-emerald-400";
  if (n < 0) return "text-red-400";
  return "text-slate-400";
}

/** Inline background color for P&L card backgrounds */
export function pnlBg(n: number): string {
  if (n > 0) return "rgba(52,211,153,0.08)";
  if (n < 0) return "rgba(248,113,113,0.08)";
  return "rgba(255,255,255,0.03)";
}
