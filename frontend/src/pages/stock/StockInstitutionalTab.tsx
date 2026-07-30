import type { InstitutionalData, MarginData } from "@/types/stock";

interface StockInstitutionalTabProps {
  institutionalData: InstitutionalData | null;
  marginData: MarginData | null;
  isTW: boolean;
}

export default function StockInstitutionalTab({
  institutionalData,
  marginData,
  isTW,
}: StockInstitutionalTabProps) {
  return (
    <div className="space-y-6">
      {/* 法人買賣超 */}
      {institutionalData && !institutionalData.error ? (
        <>
          {/* 法人匯總 Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              {
                label: "外資合計",
                value: institutionalData.foreign_total_net,
                extra: institutionalData.foreign_consecutive_days
                  ? `連續${Math.abs(institutionalData.foreign_consecutive_days)}天${institutionalData.foreign_consecutive_days > 0 ? "買超" : "賣超"}`
                  : undefined,
              },
              {
                label: "投信合計",
                value: institutionalData.investment_trust_total_net,
              },
              {
                label: "自營商合計",
                value: institutionalData.dealer_total_net,
              },
              {
                label: "三大法人合計",
                value: institutionalData.total_net,
              },
            ].map(({ label, value, extra }) => (
              <div key={label} className="card p-5">
                <p className="text-xs text-ink-muted mb-2">{label}</p>
                <p
                  className={`text-base font-bold tabular-nums ${
                    value > 0
                      ? "text-up"
                      : value < 0
                        ? "text-down"
                        : "text-ink"
                  }`}
                >
                  {value > 0 ? "+" : ""}
                  {value.toLocaleString()} 張
                </p>
                {extra && (
                  <p className="text-xs text-ink-muted mt-1">{extra}</p>
                )}
              </div>
            ))}
          </div>

          {/* 逐日明細 */}
          {institutionalData.records.length > 0 && (
            <div className="card overflow-hidden">
              <p className="text-sm text-ink-secondary px-6 pt-5 pb-3">
                法人逐日買賣超（張）
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-ink-muted border-b border-line-subtle">
                      <th className="text-left px-4 py-2.5 font-medium">
                        日期
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        外資
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        投信
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        自營商
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        合計
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {institutionalData.records.map((r) => (
                      <tr
                        key={r.date}
                        className="border-b border-line-subtle hover:bg-[var(--surface-1)]"
                      >
                        <td className="px-4 py-2.5 text-ink-secondary">{r.date}</td>
                        {[
                          r.foreign_net,
                          r.investment_trust_net,
                          r.dealer_net,
                          r.total_net,
                        ].map((v, i) => (
                          <td
                            key={i}
                            className={`px-4 py-2.5 text-right tabular-nums font-medium ${
                              v > 0
                                ? "text-up"
                                : v < 0
                                  ? "text-down"
                                  : "text-ink-muted"
                            }`}
                          >
                            {v > 0 ? "+" : ""}
                            {v.toLocaleString()}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : institutionalData?.error ? (
        <div className="card p-6 text-center">
          <p className="text-sm text-ink-muted">{institutionalData.error}</p>
        </div>
      ) : !isTW ? (
        <div className="card p-6 text-center">
          <p className="text-sm text-ink-muted">
            籌碼面資料僅支援台股（上市/上櫃）
          </p>
        </div>
      ) : null}

      {/* 融資融券 */}
      {marginData && !marginData.error ? (
        <>
          <div className="card p-6">
            <p className="text-sm text-ink-secondary mb-4">融資融券概況</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                {
                  label: "融資餘額",
                  value: marginData.latest?.margin_balance,
                  suffix: "張",
                  colored: false,
                },
                {
                  label: "融資增減",
                  value: marginData.margin_change,
                  suffix: "張",
                  colored: true,
                },
                {
                  label: "融券餘額",
                  value: marginData.latest?.short_balance,
                  suffix: "張",
                  colored: false,
                },
                {
                  label: "融券增減",
                  value: marginData.short_change,
                  suffix: "張",
                  colored: true,
                },
              ].map(({ label, value, suffix, colored }) => (
                <div key={label}>
                  <p className="text-xs text-ink-muted">{label}</p>
                  <p
                    className={`text-sm font-semibold mt-2 tabular-nums ${
                      colored
                        ? (value ?? 0) > 0
                          ? "text-up"
                          : (value ?? 0) < 0
                            ? "text-down"
                            : "text-ink"
                        : "text-ink-strong"
                    }`}
                  >
                    {value != null
                      ? `${colored && value > 0 ? "+" : ""}${value.toLocaleString()} ${suffix}`
                      : "-"}
                  </p>
                </div>
              ))}
            </div>
            {marginData.latest?.margin_utilization != null && (
              <div className="mt-5">
                <div className="flex justify-between text-xs mb-2">
                  <span className="text-ink-muted">融資使用率</span>
                  <span className="text-ink font-medium">
                    {marginData.latest.margin_utilization.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 bg-[var(--surface-3)] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-warn transition-[width]"
                    style={{
                      width: `${Math.min(marginData.latest.margin_utilization, 100)}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* 融資融券逐日明細 */}
          {marginData.records.length > 0 && (
            <div className="card overflow-hidden">
              <p className="text-sm text-ink-secondary px-6 pt-5 pb-3">
                融資融券逐日明細
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-ink-muted border-b border-line-subtle">
                      <th className="text-left px-4 py-2.5 font-medium">
                        日期
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        融資買
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        融資賣
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        融資餘額
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        融券賣
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        融券買
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        融券餘額
                      </th>
                      <th className="text-right px-4 py-2.5 font-medium">
                        資券互抵
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {marginData.records.map((r) => (
                      <tr
                        key={r.date}
                        className="border-b border-line-subtle hover:bg-[var(--surface-1)]"
                      >
                        <td className="px-4 py-2.5 text-ink-secondary">{r.date}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink">
                          {r.margin_buy.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink">
                          {r.margin_sell.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink-strong font-medium">
                          {r.margin_balance.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink">
                          {r.short_sell.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink">
                          {r.short_buy.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink-strong font-medium">
                          {r.short_balance.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-ink-secondary">
                          {r.offset.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : marginData?.error ? (
        <div className="card p-6 text-center">
          <p className="text-sm text-ink-muted">{marginData.error}</p>
        </div>
      ) : null}
    </div>
  );
}
