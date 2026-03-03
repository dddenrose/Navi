import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface RsiChartProps {
  rsi: number;
}

export default function RsiChart({ rsi }: RsiChartProps) {
  const data = [{ name: "RSI", value: rsi }];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <ReferenceLine y={70} stroke="#f87171" strokeDasharray="3 3" />
        <ReferenceLine y={30} stroke="#4ade80" strokeDasharray="3 3" />
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#64748b" }} />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#818cf8"
          strokeWidth={2}
          dot
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
