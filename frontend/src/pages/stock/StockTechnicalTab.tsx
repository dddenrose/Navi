import { lazy, Suspense } from "react";
import { TriangleAlert } from "lucide-react";
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
        <div className="card p-5">
          <p className="text-xs text-ink-muted mb-2">綜合判斷</p>
          <p className="text-sm text-ink leading-relaxed">
            {technicalData.summary}
          </p>
        </div>
      )}

      {/* RSI */}
      {technicalData.rsi_14 != null && (
        <div className="card p-6">
          <div className="flex justify-between items-center mb-4">
            <span className="text-sm text-ink-secondary">
              RSI (14)
              {technicalData.rsi_signal && (
                <span className="ml-2 text-xs text-ink-muted">
                  {technicalData.rsi_signal}
                </span>
              )}
            </span>
            <span
              className={`text-sm font-bold ${
                technicalData.rsi_14 > 70
                  ? "text-up"
                  : technicalData.rsi_14 < 30
                    ? "text-down"
                    : "text-ink-strong"
              }`}
            >
              {fmtNum(technicalData.rsi_14)}
            </span>
          </div>
          <div className="h-2 bg-[var(--surface-3)] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-[width] ${
                technicalData.rsi_14 > 70
                  ? "bg-up"
                  : technicalData.rsi_14 < 30
                    ? "bg-down"
                    : "bg-accent"
              }`}
              style={{ width: `${Math.min(technicalData.rsi_14, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-ink-faint mt-2">
            <span>超賣 &lt;30</span>
            <span>超買 &gt;70</span>
          </div>
        </div>
      )}

      {/* MACD */}
      {technicalData.macd != null && (
        <div className="card p-6">
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-ink-secondary">MACD</p>
            {technicalData.macd_cross && (
              <span className="text-xs text-ink-muted">
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
                    ? "text-down"
                    : "text-up",
              },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <p className="text-xs text-ink-muted">{label}</p>
                <p
                  className={`text-sm font-semibold mt-2 ${color ?? "text-ink-strong"}`}
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
        <div className="card p-6">
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-ink-secondary">KD 指標</p>
            {technicalData.kd_signal && (
              <span className="text-xs text-ink-muted">
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
                <p className="text-xs text-ink-muted">{label}</p>
                <p className="text-sm font-semibold mt-2 text-ink-strong">
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Moving Averages */}
      <div className="card p-6">
        <div className="flex justify-between items-center mb-4">
          <p className="text-sm text-ink-secondary">均線</p>
          {technicalData.ma_trend && (
            <span className="text-xs text-ink-muted">
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
              <p className="text-xs text-ink-muted">{label}</p>
              <p
                className={`text-sm font-semibold mt-2 ${
                  value != null && (priceData.price ?? 0) > value
                    ? "text-down"
                    : value != null
                      ? "text-up"
                      : "text-ink-muted"
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
        <div className="card p-6">
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-ink-secondary">布林通道</p>
            {technicalData.bb_position && (
              <span className="text-xs text-ink-muted">
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
                <p className="text-xs text-ink-muted">{label}</p>
                <p className="text-sm font-semibold mt-2 text-ink-strong">
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* RSI Chart */}
      {technicalData.rsi_14 != null && (
        <div className="card p-6 h-52">
          <p className="text-xs text-ink-muted mb-3">RSI 視覺化</p>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full text-xs text-ink-faint">
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
        <div className="card p-6">
          <p className="text-sm text-ink-secondary mb-4">支撐 / 阻力</p>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <p className="text-xs text-down mb-3">支撐位</p>
              {technicalData.supports?.length ? (
                <div className="space-y-2">
                  {technicalData.supports.map(([label, val]) => (
                    <div key={label} className="flex justify-between text-sm">
                      <span className="text-ink-muted">{label}</span>
                      <span className="text-down font-semibold tabular-nums">
                        {fmtNum(val)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-ink-faint">-</p>
              )}
            </div>
            <div>
              <p className="text-xs text-up mb-3">阻力位</p>
              {technicalData.resistances?.length ? (
                <div className="space-y-2">
                  {technicalData.resistances.map(([label, val]) => (
                    <div key={label} className="flex justify-between text-sm">
                      <span className="text-ink-muted">{label}</span>
                      <span className="text-up font-semibold tabular-nums">
                        {fmtNum(val)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-ink-faint">-</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Fibonacci Levels */}
      {technicalData.fibonacci_levels &&
        Object.keys(technicalData.fibonacci_levels).length > 0 && (
          <div className="card p-6">
            <div className="flex justify-between items-center mb-4">
              <p className="text-sm text-ink-secondary">費波那契回檔</p>
              <span className="text-xs text-ink-faint">
                高 {fmtNum(technicalData.swing_high)} / 低{" "}
                {fmtNum(technicalData.swing_low)}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(technicalData.fibonacci_levels).map(
                ([level, val]) => (
                  <div key={level}>
                    <p className="text-xs text-ink-muted">{level}</p>
                    <p className="text-sm font-semibold mt-1 text-warn tabular-nums">
                      {fmtNum(val)}
                    </p>
                  </div>
                ),
              )}
            </div>
          </div>
        )}

      {/* 趨勢警戒參考位（教育性資訊，非停損指令） */}
      {technicalData.stop_loss != null && (
        <div className="card p-6">
          <p className="text-sm text-ink-secondary mb-4">趨勢警戒參考位</p>
          <div className="grid grid-cols-2 gap-5 mb-4">
            <div>
              <p className="text-xs text-ink-muted">技術警戒位</p>
              <p className="text-lg font-bold text-up mt-1 tabular-nums">
                {fmtNum(technicalData.stop_loss)}
              </p>
            </div>
            {technicalData.current_price != null && (
              <div>
                <p className="text-xs text-ink-muted">距目前價差</p>
                <p className="text-lg font-bold text-ink mt-1 tabular-nums">
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
            <p className="text-xs text-ink-muted leading-relaxed mb-2">
              {technicalData.stop_loss_note}
            </p>
          )}
          <p className="text-xs text-ink-muted leading-relaxed">
            此為技術面觀察位置，非停損或進出場指令；請依自身投資週期與風險承受度判斷。
          </p>
        </div>
      )}

      <p className="flex items-start gap-1.5 text-xs text-ink-muted leading-relaxed">
        <TriangleAlert
          size={14}
          className="text-warn shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <span>
          以上技術分析僅供學習與研究用途，不構成投資建議；資料可能延遲，交易前請以券商報價為準。
        </span>
      </p>
    </div>
  );
}
