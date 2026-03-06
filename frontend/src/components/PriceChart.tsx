import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface PriceChartProps {
  history: Array<{ date: string; close: number }>;
  isPositive: boolean;
}

export default function PriceChart({ history, isPositive }: PriceChartProps) {
  const root = getComputedStyle(document.documentElement);
  const grid = root.getPropertyValue("--chart-grid").trim() || "#334155";
  const tick = root.getPropertyValue("--chart-tick").trim() || "#64748b";
  const tooltipBg =
    root.getPropertyValue("--tooltip-bg").trim() || "rgba(13,20,36,0.95)";
  const tooltipBorder =
    root.getPropertyValue("--tooltip-border").trim() ||
    "rgba(255,255,255,0.08)";

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={history}>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: tick }}
          tickLine={false}
          axisLine={false}
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
        />
        <Line
          type="monotone"
          dataKey="close"
          stroke={isPositive ? "#4ade80" : "#f87171"}
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
