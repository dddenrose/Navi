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
              <div
                key={label}
                className="rounded-2xl p-5"
                style={{
                  background: "var(--card-bg)",
                  border: "1px solid var(--border)",
                }}
              >
                <p className="text-xs text-slate-500 mb-2">{label}</p>
                <p
                  className={`text-base font-bold tabular-nums ${
                    value > 0
                      ? "text-red-400"
                      : value < 0
                        ? "text-green-400"
                        : "text-slate-300"
                  }`}
                >
                  {value > 0 ? "+" : ""}
                  {value.toLocaleString()} 張
                </p>
                {extra && (
                  <p className="text-xs text-slate-500 mt-1">{extra}</p>
                )}
              </div>
            ))}
          </div>

          {/* 逐日明細 */}
          {institutionalData.records.length > 0 && (
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                background: "var(--card-bg)",
                border: "1px solid var(--border)",
              }}
            >
              <p className="text-sm text-slate-400 px-6 pt-5 pb-3">
                法人逐日買賣超（張）
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-white/5">
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
                        className="border-b border-white/5 hover:bg-white/[0.02]"
                      >
                        <td className="px-4 py-2.5 text-slate-400">{r.date}</td>
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
                                ? "text-red-400"
                                : v < 0
                                  ? "text-green-400"
                                  : "text-slate-500"
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
        <div
          className="rounded-2xl p-6 text-center"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-sm text-slate-500">{institutionalData.error}</p>
        </div>
      ) : !isTW ? (
        <div
          className="rounded-2xl p-6 text-center"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-sm text-slate-500">
            籌碼面資料僅支援台股（上市/上櫃）
          </p>
        </div>
      ) : null}

      {/* 融資融券 */}
      {marginData && !marginData.error ? (
        <>
          <div
            className="rounded-2xl p-6"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-sm text-slate-400 mb-4">融資融券概況</p>
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
                  <p className="text-xs text-slate-500">{label}</p>
                  <p
                    className={`text-sm font-semibold mt-2 tabular-nums ${
                      colored
                        ? (value ?? 0) > 0
                          ? "text-red-400"
                          : (value ?? 0) < 0
                            ? "text-green-400"
                            : "text-slate-300"
                        : "text-slate-100"
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
                  <span className="text-slate-500">融資使用率</span>
                  <span className="text-slate-300 font-medium">
                    {marginData.latest.margin_utilization.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-amber-400 transition-[width]"
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
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                background: "var(--card-bg)",
                border: "1px solid var(--border)",
              }}
            >
              <p className="text-sm text-slate-400 px-6 pt-5 pb-3">
                融資融券逐日明細
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-white/5">
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
                        className="border-b border-white/5 hover:bg-white/[0.02]"
                      >
                        <td className="px-4 py-2.5 text-slate-400">{r.date}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                          {r.margin_buy.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                          {r.margin_sell.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-100 font-medium">
                          {r.margin_balance.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                          {r.short_sell.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">
                          {r.short_buy.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-100 font-medium">
                          {r.short_balance.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">
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
        <div
          className="rounded-2xl p-6 text-center"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <p className="text-sm text-slate-500">{marginData.error}</p>
        </div>
      ) : null}
    </div>
  );
}
