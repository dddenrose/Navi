import { useId, useMemo } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useThemeStore } from "@/store/themeStore";
import { useReducedMotion } from "@/lib/useReducedMotion";
import type { PricePoint } from "@/types/stock";

interface PriceChartProps {
  history: PricePoint[];
  isPositive: boolean;
}

/** "2026-05-26" → "05/26"；非預期格式原樣回傳。 */
function shortDate(value: string): string {
  const parts = value.split("-");
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : value;
}

export default function PriceChart({ history, isPositive }: PriceChartProps) {
  // Read CSS variables once per theme change, not on every render.
  // `theme` is a deliberate dep so we re-read CSS vars when the theme switches;
  // `getComputedStyle` reads from DOM, not from `theme` directly, hence disable.
  const { theme } = useThemeStore();
  const reducedMotion = useReducedMotion();
  const gradientId = useId();

  const { grid, tick, tooltipBg, tooltipBorder, lineColor } = useMemo(() => {
    const root = getComputedStyle(document.documentElement);
    return {
      grid: root.getPropertyValue("--chart-grid").trim() || "#334155",
      tick: root.getPropertyValue("--chart-tick").trim() || "#64748b",
      tooltipBg:
        root.getPropertyValue("--tooltip-bg").trim() || "rgba(13,20,36,0.95)",
      tooltipBorder:
        root.getPropertyValue("--tooltip-border").trim() ||
        "rgba(255,255,255,0.08)",
      lineColor:
        root
          .getPropertyValue(isPositive ? "--market-up" : "--market-down")
          .trim() || (isPositive ? "#f26d6d" : "#3ecf8e"),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme, isPositive]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={history}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity={0.12} />
            <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: tick }}
          tickLine={false}
          axisLine={false}
          tickFormatter={shortDate}
          minTickGap={40}
        />
        <YAxis
          tick={{ fontSize: 10, fill: tick }}
          tickLine={false}
          axisLine={false}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{
            background: tooltipBg,
            border: `1px solid ${tooltipBorder}`,
            borderRadius: "12px",
            backdropFilter: "blur(12px)",
          }}
          labelStyle={{ color: tick, fontSize: "11px" }}
          itemStyle={{ color: "var(--accent)", fontSize: "12px" }}
          formatter={(value: number | undefined) => [
            value?.toFixed(2) ?? "—",
            "收盤",
          ]}
        />
        <Area
          type="monotone"
          dataKey="close"
          stroke="none"
          fill={`url(#${gradientId})`}
          isAnimationActive={!reducedMotion}
          animationDuration={800}
          animationEasing="ease-out"
        />
        <Line
          type="monotone"
          dataKey="close"
          stroke={lineColor}
          strokeWidth={2}
          dot={false}
          isAnimationActive={!reducedMotion}
          animationDuration={800}
          animationEasing="ease-out"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
