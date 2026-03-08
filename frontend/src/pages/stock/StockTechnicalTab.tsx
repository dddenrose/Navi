import { lazy, Suspense } from "react";
import { fmtNum } from "@/lib/format";
import type { Technicals, StockPrice } from "@/types/stock";

// bundle-dynamic-imports: defer recharts until chart is visible
const RsiChart = lazy(() => import("@/components/RsiChart"));

interface StockTechnicalTabProps {
  technicalData: Technicals;
  priceData: StockPrice;
}

export default function StockTechnicalTab({
  technicalData,
  priceData,
}: StockTechnicalTabProps) {
  return (
    <div className="space-y-6">
      {/* 綜合判斷 */}
      {technicalData.summary && (
        <div
          className="rounded-2xl p-5"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-xs text-slate-500 mb-2">綜合判斷</p>
          <p className="text-sm text-slate-300 leading-relaxed">
            {technicalData.summary}
          </p>
        </div>
      )}

      {/* RSI */}
      {technicalData.rsi_14 != null && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex justify-between items-center mb-4">
            <span className="text-sm text-slate-400">
              RSI (14)
              {technicalData.rsi_signal && (
                <span className="ml-2 text-xs text-slate-500">
                  {technicalData.rsi_signal}
                </span>
              )}
            </span>
            <span
              className={`text-sm font-bold ${
                technicalData.rsi_14 > 70
                  ? "text-red-400"
                  : technicalData.rsi_14 < 30
                    ? "text-green-400"
                    : "text-slate-100"
              }`}
            >
              {fmtNum(technicalData.rsi_14)}
            </span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-[width] ${
                technicalData.rsi_14 > 70
                  ? "bg-red-400"
                  : technicalData.rsi_14 < 30
                    ? "bg-green-400"
                    : "bg-indigo-400"
              }`}
              style={{ width: `${Math.min(technicalData.rsi_14, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-600 mt-2">
            <span>超賣 &lt;30</span>
            <span>超買 &gt;70</span>
          </div>
        </div>
      )}

      {/* MACD */}
      {technicalData.macd != null && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-slate-400">MACD</p>
            {technicalData.macd_cross && (
              <span className="text-xs text-slate-500">
                {technicalData.macd_cross}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3 md:gap-5">
            {[
              { label: "DIF", value: fmtNum(technicalData.macd) },
              { label: "DEA", value: fmtNum(technicalData.macd_signal) },
              {
                label: "Histogram",
                value: fmtNum(technicalData.macd_histogram),
                color:
                  (technicalData.macd_histogram ?? 0) >= 0
                    ? "text-green-400"
                    : "text-red-400",
              },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <p className="text-xs text-slate-500">{label}</p>
                <p
                  className={`text-sm font-semibold mt-2 ${color ?? "text-slate-100"}`}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* KD */}
      {technicalData.k_value != null && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-slate-400">KD 指標</p>
            {technicalData.kd_signal && (
              <span className="text-xs text-slate-500">
                {technicalData.kd_signal}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 md:gap-5">
            {[
              { label: "K 值", value: fmtNum(technicalData.k_value) },
              { label: "D 值", value: fmtNum(technicalData.d_value) },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-xs text-slate-500">{label}</p>
                <p className="text-sm font-semibold mt-2 text-slate-100">
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Moving Averages */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex justify-between items-center mb-4">
          <p className="text-sm text-slate-400">均線</p>
          {technicalData.ma_trend && (
            <span className="text-xs text-slate-500">
              {technicalData.ma_trend}
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
          {[
            { label: "MA5", value: technicalData.ma5 },
            { label: "MA10", value: technicalData.ma10 },
            { label: "MA20", value: technicalData.ma20 },
            { label: "MA60", value: technicalData.ma60 },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="text-xs text-slate-500">{label}</p>
              <p
                className={`text-sm font-semibold mt-2 ${
                  value != null && (priceData.price ?? 0) > value
                    ? "text-green-400"
                    : value != null
                      ? "text-red-400"
                      : "text-slate-500"
                }`}
              >
                {value != null ? fmtNum(value) : "-"}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Bollinger Bands */}
      {technicalData.bb_upper != null && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-slate-400">布林通道</p>
            {technicalData.bb_position && (
              <span className="text-xs text-slate-500">
                {technicalData.bb_position}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3 md:gap-5">
            {[
              { label: "上軌", value: fmtNum(technicalData.bb_upper) },
              { label: "中軌", value: fmtNum(technicalData.bb_middle) },
              { label: "下軌", value: fmtNum(technicalData.bb_lower) },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-xs text-slate-500">{label}</p>
                <p className="text-sm font-semibold mt-2 text-slate-100">
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* RSI Chart */}
      {technicalData.rsi_14 != null && (
        <div
          className="rounded-2xl p-6 h-52"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-xs text-slate-500 mb-3">RSI 視覺化</p>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full text-xs text-slate-600">
                圖表載入中…
              </div>
            }
          >
            <RsiChart rsi={technicalData.rsi_14} />
          </Suspense>
        </div>
      )}

      {/* Support / Resistance */}
      {((technicalData.supports?.length ?? 0) > 0 ||
        (technicalData.resistances?.length ?? 0) > 0) && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-sm text-slate-400 mb-4">支撐 / 阻力</p>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <p className="text-xs text-green-400 mb-3">支撐位</p>
              {technicalData.supports?.length ? (
                <div className="space-y-2">
                  {technicalData.supports.map(([label, val]) => (
                    <div key={label} className="flex justify-between text-sm">
                      <span className="text-slate-500">{label}</span>
                      <span className="text-green-400 font-semibold tabular-nums">
                        {fmtNum(val)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-600">-</p>
              )}
            </div>
            <div>
              <p className="text-xs text-red-400 mb-3">阻力位</p>
              {technicalData.resistances?.length ? (
                <div className="space-y-2">
                  {technicalData.resistances.map(([label, val]) => (
                    <div key={label} className="flex justify-between text-sm">
                      <span className="text-slate-500">{label}</span>
                      <span className="text-red-400 font-semibold tabular-nums">
                        {fmtNum(val)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-600">-</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Fibonacci Levels */}
      {technicalData.fibonacci_levels &&
        Object.keys(technicalData.fibonacci_levels).length > 0 && (
          <div
            className="rounded-2xl p-6"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="flex justify-between items-center mb-4">
              <p className="text-sm text-slate-400">費波那契回檔</p>
              <span className="text-xs text-slate-600">
                高 {fmtNum(technicalData.swing_high)} / 低{" "}
                {fmtNum(technicalData.swing_low)}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(technicalData.fibonacci_levels).map(
                ([level, val]) => (
                  <div key={level}>
                    <p className="text-xs text-slate-500">{level}</p>
                    <p className="text-sm font-semibold mt-1 text-amber-400 tabular-nums">
                      {fmtNum(val)}
                    </p>
                  </div>
                ),
              )}
            </div>
          </div>
        )}

      {/* Stop Loss & Risk/Reward */}
      {technicalData.stop_loss != null && (
        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-sm text-slate-400 mb-4">停損建議 / 風報比</p>
          <div className="grid grid-cols-2 gap-5 mb-4">
            <div>
              <p className="text-xs text-slate-500">建議停損價</p>
              <p className="text-lg font-bold text-red-400 mt-1 tabular-nums">
                {fmtNum(technicalData.stop_loss)}
              </p>
            </div>
            {technicalData.current_price != null && (
              <div>
                <p className="text-xs text-slate-500">距目前價差</p>
                <p className="text-lg font-bold text-slate-200 mt-1 tabular-nums">
                  {(
                    ((technicalData.stop_loss - technicalData.current_price) /
                      technicalData.current_price) *
                    100
                  ).toFixed(2)}
                  %
                </p>
              </div>
            )}
          </div>
          {technicalData.stop_loss_note && (
            <p className="text-xs text-slate-500 leading-relaxed mb-2">
              {technicalData.stop_loss_note}
            </p>
          )}
          {technicalData.risk_reward_note && (
            <p className="text-xs text-slate-500 leading-relaxed">
              {technicalData.risk_reward_note}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
