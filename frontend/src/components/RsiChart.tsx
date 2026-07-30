import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { useThemeStore } from "@/store/themeStore";
import { useReducedMotion } from "@/lib/useReducedMotion";

interface RsiChartProps {
  rsi: number;
}

export default function RsiChart({ rsi }: RsiChartProps) {
  const data = [{ name: "RSI", value: rsi }];
  // Read CSS variables once per theme change, not on every render.
  // `theme` is a deliberate dep to retrigger DOM CSS-var read when theme switches.
  const { theme } = useThemeStore();
  const reducedMotion = useReducedMotion();
  const { grid, tick, up, down, accent } = useMemo(() => {
    const root = getComputedStyle(document.documentElement);
    return {
      grid: root.getPropertyValue("--chart-grid").trim() || "#334155",
      tick: root.getPropertyValue("--chart-tick").trim() || "#64748b",
      up: root.getPropertyValue("--market-up").trim() || "#f26d6d",
      down: root.getPropertyValue("--market-down").trim() || "#3ecf8e",
      accent: root.getPropertyValue("--accent").trim() || "#8ab4ff",
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <ReferenceLine y={70} stroke={up} strokeDasharray="3 3" />
        <ReferenceLine y={30} stroke={down} strokeDasharray="3 3" />
        <CartesianGrid strokeDasharray="3 3" stroke={grid} />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: tick }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: tick }} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={accent}
          strokeWidth={2}
          dot
          isAnimationActive={!reducedMotion}
          animationDuration={800}
          animationEasing="ease-out"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
