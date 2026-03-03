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
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={history}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(13,20,36,0.95)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "12px",
            backdropFilter: "blur(12px)",
          }}
          labelStyle={{ color: "#64748b", fontSize: "11px" }}
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
