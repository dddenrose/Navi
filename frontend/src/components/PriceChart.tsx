import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useThemeStore } from "@/store/themeStore";
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
  const { grid, tick, tooltipBg, tooltipBorder } = useMemo(() => {
    const root = getComputedStyle(document.documentElement);
    return {
      grid: root.getPropertyValue("--chart-grid").trim() || "#334155",
      tick: root.getPropertyValue("--chart-tick").trim() || "#64748b",
      tooltipBg:
        root.getPropertyValue("--tooltip-bg").trim() || "rgba(13,20,36,0.95)",
      tooltipBorder:
        root.getPropertyValue("--tooltip-border").trim() ||
        "rgba(255,255,255,0.08)",
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={history}>
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
          itemStyle={{ color: "#818cf8", fontSize: "12px" }}
          formatter={(value: number | undefined) => [
            value?.toFixed(2) ?? "—",
            "收盤",
          ]}
        />
        <Line
          type="monotone"
          dataKey="close"
          stroke={isPositive ? "#f87171" : "#4ade80"}
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
