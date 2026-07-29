import { useAdminUsageSummary } from "@/lib/queries/admin";

export default function AdminDashboard() {
  const { data, isPending, error } = useAdminUsageSummary(30);

  if (isPending) return <p className="text-sm text-slate-500">載入中…</p>;
  if (error) return <p className="text-sm text-rose-400">{String(error)}</p>;
  if (!data) return null;

  const maxCount = Math.max(1, ...data.daily_breakdown.map((d) => d.count));

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Stat label="近 30 天訊息總數" value={data.total_messages} />
        <Stat label="活躍使用者" value={data.active_users} />
        <Stat
          label="平均每人訊息"
          value={
            data.active_users
              ? Math.round((data.total_messages / data.active_users) * 10) / 10
              : 0
          }
        />
      </div>

      <Card title="每日用量">
        <div className="flex items-end gap-1 h-32">
          {data.daily_breakdown.map((d) => (
            <div
              key={d.date}
              className="flex-1 group relative flex flex-col justify-end"
              title={`${d.date}: ${d.count}`}
            >
              <div
                className="w-full rounded-t"
                style={{
                  height: `${(d.count / maxCount) * 100}%`,
                  background:
                    "linear-gradient(180deg, rgba(99,102,241,0.9), rgba(139,92,246,0.5))",
                  minHeight: d.count > 0 ? "4px" : "1px",
                }}
              />
            </div>
          ))}
        </div>
        <div className="flex justify-between text-[10px] text-slate-600 mt-2">
          <span>{data.daily_breakdown[0]?.date}</span>
          <span>
            {data.daily_breakdown[data.daily_breakdown.length - 1]?.date}
          </span>
        </div>
      </Card>

      <Card title="Top 10 使用者">
        {data.top_users.length === 0 ? (
          <p className="text-xs text-slate-600">尚無資料</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-600">
                <th className="text-left py-2">UID</th>
                <th className="text-right py-2">訊息數</th>
              </tr>
            </thead>
            <tbody>
              {data.top_users.map((u) => (
                <tr key={u.uid} className="border-t border-white/5">
                  <td className="py-2 font-mono text-slate-300">{u.uid}</td>
                  <td className="py-2 text-right text-slate-200">{u.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <p className="text-xs text-slate-600 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <h3 className="text-sm font-semibold text-slate-200 mb-3">{title}</h3>
      {children}
    </div>
  );
}
