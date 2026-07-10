import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getReport,
  getSubscription,
  getTrackingSummary,
  listReports,
  updateSubscription,
} from "@/lib/api/screener";
import type {
  FinalGrade,
  PickDoc,
  ReportDetail,
  ReportSummary,
  RuleCheck,
  ScreenerFrequency,
  ScreenerProfile,
  TrackingSummary,
  ValueTrapCheck,
} from "@/types/screener";

// ── Formatters ─────────────────────────────────────────────────────────────

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}
function fmtSigned(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}%`;
}
function fmtRule(v: string | number | null): string {
  if (v == null) return "—";
  return String(v);
}
function fmtSignedPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(digits)}%`;
}
function pnlColor(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "text-slate-500";
  return v >= 0 ? "text-emerald-400" : "text-red-400";
}

function reportTimestamp(value: ReportSummary["generated_at"]): Date | null {
  if (!value) return null;
  if (typeof value === "string") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  const seconds = value.seconds ?? value._seconds;
  if (typeof seconds !== "number") return null;
  return new Date(seconds * 1000);
}

function reportDateFromId(reportId: string): Date | null {
  const match = reportId.match(/^(\d{4})(\d{2})(\d{2})/);
  if (!match) return null;
  const [, year, month, day] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function reportDate(summary: ReportSummary): Date | null {
  return (
    reportTimestamp(summary.generated_at) ?? reportDateFromId(summary.report_id)
  );
}

function fmtReportDate(summary: ReportSummary, compact = false): string {
  const date = reportDate(summary);
  if (!date) return summary.report_id;
  return date.toLocaleDateString("zh-TW", {
    year: compact ? undefined : "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// ── Visual tokens ──────────────────────────────────────────────────────────

function gradeStyle(grade: FinalGrade): {
  text: string;
  bg: string;
  label: string;
} {
  switch (grade) {
    case "Strong Pick":
      return {
        text: "text-emerald-300",
        bg: "bg-emerald-400/15 border-emerald-500/30",
        label: "Strong Pick",
      };
    case "Pick":
      return {
        text: "text-sky-300",
        bg: "bg-sky-400/15 border-sky-500/30",
        label: "Pick",
      };
    case "Watch":
      return {
        text: "text-amber-300",
        bg: "bg-amber-400/15 border-amber-500/30",
        label: "Watch",
      };
    default:
      return {
        text: "text-slate-400",
        bg: "bg-slate-500/15 border-slate-500/30",
        label: String(grade || "—"),
      };
  }
}

function valueTrapStyle(c: ValueTrapCheck | undefined): { text: string; label: string } {
  switch (c) {
    case "no_concern":
      return { text: "text-emerald-400", label: "無重大疑慮" };
    case "watch":
      return { text: "text-amber-400", label: "觀察" };
    case "warning":
      return { text: "text-red-400", label: "疑似價值陷阱" };
    default:
      // 未知列舉值以警示色呈現（寧可誤警不可漏警）；無值維持中性
      return c
        ? { text: "text-red-400", label: String(c) }
        : { text: "text-slate-400", label: "—" };
  }
}

// ── ProfileTabs ────────────────────────────────────────────────────────────

function ProfileTabs({
  profile,
  frequency,
  onProfile,
  onFrequency,
}: {
  profile: ScreenerProfile;
  frequency: ScreenerFrequency;
  onProfile: (p: ScreenerProfile) => void;
  onFrequency: (f: ScreenerFrequency) => void;
}) {
  const profiles: { key: ScreenerProfile; label: string; emoji: string }[] = [
    { key: "momentum", label: "Momentum Rider", emoji: "🚀" },
    { key: "value", label: "Value Hunter", emoji: "💎" },
  ];
  const freqs: { key: ScreenerFrequency; label: string }[] = [
    { key: "weekly", label: "週報" },
    { key: "daily", label: "日報" },
  ];
  return (
    <div className="flex flex-wrap gap-3 items-center">
      <div
        className="inline-flex p-1 rounded-xl"
        style={{ background: "var(--overlay-bg)" }}
      >
        {profiles.map((p) => (
          <button
            key={p.key}
            onClick={() => onProfile(p.key)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
              profile === p.key
                ? "text-white"
                : "text-slate-500 hover:text-slate-300"
            }`}
            style={
              profile === p.key
                ? {
                    background:
                      "linear-gradient(135deg, rgba(99,102,241,0.35), rgba(139,92,246,0.25))",
                  }
                : {}
            }
          >
            <span className="mr-1">{p.emoji}</span>
            {p.label}
          </button>
        ))}
      </div>
      <div
        className="inline-flex p-1 rounded-xl"
        style={{ background: "var(--overlay-bg)" }}
      >
        {freqs.map((f) => (
          <button
            key={f.key}
            onClick={() => onFrequency(f.key)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
              frequency === f.key
                ? "text-white bg-white/10"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── IndustryChips ─────────────────────────────────────────────────────────

function IndustryChips({
  industries,
  selected,
  onSelect,
  counts,
}: {
  industries: string[];
  selected: string | null;
  onSelect: (i: string | null) => void;
  counts: Record<string, number>;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onSelect(null)}
        className={`px-3 py-1 text-xs rounded-full transition-colors ${
          selected === null
            ? "text-white"
            : "text-slate-500 hover:text-slate-300"
        }`}
        style={{
          background:
            selected === null
              ? "linear-gradient(135deg, rgba(99,102,241,0.35), rgba(139,92,246,0.25))"
              : "var(--overlay-bg)",
          border: "1px solid var(--border)",
        }}
      >
        全部 ({Object.values(counts).reduce((a, b) => a + b, 0)})
      </button>
      {industries.map((ind) => (
        <button
          key={ind}
          onClick={() => onSelect(ind)}
          className={`px-3 py-1 text-xs rounded-full transition-colors ${
            selected === ind
              ? "text-white"
              : "text-slate-500 hover:text-slate-300"
          }`}
          style={{
            background:
              selected === ind
                ? "linear-gradient(135deg, rgba(99,102,241,0.35), rgba(139,92,246,0.25))"
                : "var(--overlay-bg)",
            border: "1px solid var(--border)",
          }}
        >
          {ind} ({counts[ind] || 0})
        </button>
      ))}
    </div>
  );
}

// ── PickCard ──────────────────────────────────────────────────────────────

function GradeBadge({ grade }: { grade: FinalGrade }) {
  const s = gradeStyle(grade);
  return (
    <span
      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${s.text} ${s.bg}`}
    >
      {s.label}
    </span>
  );
}

function PickCard({ pick, onClick }: { pick: PickDoc; onClick: () => void }) {
  const v = pick.valuation;
  const upside = v?.implied_upside_mid_pct;
  const trap = pick.interpretation?.value_trap_check;
  const trapStyle = trap ? valueTrapStyle(trap) : null;

  return (
    <button
      onClick={onClick}
      className="text-left rounded-2xl p-4 md:p-5 transition-all hover:scale-[1.01] hover:border-indigo-500/40"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-slate-100">
              {pick.name || pick.ticker}
            </h3>
            <span className="text-xs text-slate-500">
              {pick.ticker.replace(".TW", "").replace(".TWO", "")}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            #{pick.rank_in_industry}/{pick.industry_size} · {pick.industry}
          </p>
        </div>
        <GradeBadge grade={pick.final_grade} />
      </div>

      <p className="text-xs text-slate-400 line-clamp-3 mb-3 leading-relaxed">
        {pick.interpretation?.narrative || "—"}
      </p>

      <div className="grid grid-cols-3 gap-2 text-xs tabular-nums">
        <div>
          <p className="text-slate-600">現價</p>
          <p className="text-slate-200">${fmtNum(pick.snapshot.price)}</p>
        </div>
        <div>
          <p className="text-slate-600">合理中值</p>
          <p className="text-slate-200">${fmtNum(v?.fair_value_mid)}</p>
        </div>
        <div>
          <p className="text-slate-600">上行</p>
          <p
            className={
              upside == null
                ? "text-slate-500"
                : upside >= 0
                  ? "text-emerald-400"
                  : "text-red-400"
            }
          >
            {fmtSigned(upside)}
          </p>
        </div>
      </div>

      {trapStyle && (
        <div className="mt-3 pt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
          <span className="text-slate-500">價值陷阱檢查</span>
          <span className={trapStyle.text}>{trapStyle.label}</span>
        </div>
      )}
    </button>
  );
}

// ── TrackingPanel（推薦實績追蹤）───────────────────────────────────────────

const TRACKING_HORIZONS: { key: string; label: string }[] = [
  { key: "t5", label: "T+5" },
  { key: "t20", label: "T+20" },
  { key: "t60", label: "T+60" },
];

function TrackingPanel({ profile }: { profile: ScreenerProfile }) {
  const [summary, setSummary] = useState<TrackingSummary | null>(null);

  useEffect(() => {
    let active = true;
    setSummary(null);
    getTrackingSummary(profile).then((s) => active && setSummary(s));
    return () => {
      active = false;
    };
  }, [profile]);

  if (!summary || !summary.pick_events) return null;

  return (
    <div
      className="rounded-2xl p-4 md:p-5 mb-6"
      style={{ background: "var(--card-bg)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <h3 className="text-sm font-medium text-slate-200">📈 推薦實績追蹤</h3>
        <span className="text-[11px] text-slate-500">
          {summary.pick_events} 次推薦事件 · {summary.report_count} 份報告
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {TRACKING_HORIZONS.map(({ key, label }) => {
          const h = summary.horizons?.[key];
          if (!h || h.n === 0) {
            return (
              <div
                key={key}
                className="rounded-xl p-3"
                style={{ background: "var(--overlay-bg)" }}
              >
                <p className="text-[11px] text-slate-500 mb-1">{label} 交易日</p>
                <p className="text-sm text-slate-600">樣本累積中…</p>
              </div>
            );
          }
          return (
            <div
              key={key}
              className="rounded-xl p-3"
              style={{ background: "var(--overlay-bg)" }}
            >
              <p className="text-[11px] text-slate-500 mb-1">
                {label} 交易日 · n={h.n}
              </p>
              <p className={`text-lg font-semibold ${pnlColor(h.avg_return)}`}>
                {fmtSignedPct(h.avg_return)}
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                勝率 {fmtPct(h.win_rate, 0)}
                {h.avg_excess != null && (
                  <>
                    {" "}· 超額大盤{" "}
                    <span className={pnlColor(h.avg_excess)}>
                      {fmtSignedPct(h.avg_excess)}
                    </span>
                  </>
                )}
              </p>
            </div>
          );
        })}
      </div>
      {summary.methodology && (
        <p className="text-[11px] text-slate-600 mt-3 leading-relaxed">
          {summary.methodology}
        </p>
      )}
    </div>
  );
}

// ── Detail components ──────────────────────────────────────────────────────

function RuleRow({ c }: { c: RuleCheck }) {
  const icon = c.passed ? "✓" : "✗";
  const iconColor = c.passed
    ? "text-emerald-400"
    : c.severity === "critical"
      ? "text-red-400"
      : "text-amber-400";
  const isMissing = String(c.actual ?? "").startsWith("資料不足");
  return (
    <div
      className="flex items-start gap-3 py-2 px-3 rounded-lg text-xs"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <span className={`font-mono font-bold ${iconColor} pt-0.5`}>{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="font-semibold text-slate-200">{c.name}</span>
          <span className="text-[10px] text-slate-500 font-mono">
            {c.rule_id}
          </span>
        </div>
        <p className="text-slate-500 mt-0.5">{c.rule}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px]">
          <span className={isMissing ? "text-amber-400/90" : "text-slate-300"}>
            實際：{fmtRule(c.actual)}
          </span>
          {c.reference != null && c.reference !== "" && (
            <span className="text-slate-500">門檻：{fmtRule(c.reference)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function CheckSection({
  title,
  summary,
  checks,
  emptyHint,
}: {
  title: string;
  summary?: string;
  checks: RuleCheck[];
  emptyHint?: string;
}) {
  return (
    <section className="mb-5">
      <div className="flex items-baseline justify-between mb-2">
        <h4 className="text-xs uppercase tracking-wider text-slate-400">
          {title}
        </h4>
        {summary && (
          <span className="text-[11px] text-slate-500">{summary}</span>
        )}
      </div>
      {checks.length === 0 ? (
        <p className="text-[11px] text-slate-600 italic">{emptyHint || "—"}</p>
      ) : (
        <div className="space-y-1.5">
          {checks.map((c) => (
            <RuleRow key={c.rule_id} c={c} />
          ))}
        </div>
      )}
    </section>
  );
}

function ValuationBand({ pick }: { pick: PickDoc }) {
  const v = pick.valuation;
  const price = pick.snapshot.price ?? null;
  const low = v?.fair_value_low ?? null;
  const mid = v?.fair_value_mid ?? null;
  const high = v?.fair_value_high ?? null;
  const buy = v?.buy_zone_upper ?? null;
  if (low == null || mid == null || high == null || price == null) {
    return (
      <div
        className="rounded-xl p-4 text-xs text-slate-500"
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
        }}
      >
        估值資料不足
      </div>
    );
  }

  // 把 low/mid/high/price/buy 投影到 0~100% 軸
  const min = Math.min(low, price) * 0.95;
  const max = Math.max(high, price) * 1.05;
  const span = max - min || 1;
  const pos = (val: number) =>
    `${Math.max(0, Math.min(100, ((val - min) / span) * 100))}%`;

  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="text-xs uppercase tracking-wider text-slate-400">
          估值區間（{v?.method || "—"}）
        </h4>
        <span
          className={`text-xs tabular-nums ${
            (v?.implied_upside_mid_pct ?? 0) >= 0
              ? "text-emerald-400"
              : "text-red-400"
          }`}
        >
          上行 {fmtSigned(v?.implied_upside_mid_pct)}
        </span>
      </div>

      {/* 帶狀圖 */}
      <div className="relative h-9 mb-2">
        <div
          className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full"
          style={{ background: "var(--overlay-bg)" }}
        />
        {/* fair value band low~high */}
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full"
          style={{
            left: pos(low),
            width: `calc(${pos(high)} - ${pos(low)})`,
            background:
              "linear-gradient(90deg, rgba(99,102,241,0.6), rgba(139,92,246,0.6))",
          }}
        />
        {/* buy zone */}
        {buy != null && (
          <div
            className="absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full"
            style={{
              left: pos(low),
              width: `calc(${pos(buy)} - ${pos(low)})`,
              background: "rgba(16,185,129,0.45)",
            }}
            title="估值偏低參考區（非買進建議）"
          />
        )}
        {/* mid marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3 rounded"
          style={{ left: pos(mid), background: "rgba(255,255,255,0.6)" }}
        />
        {/* current price marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-2 h-5 rounded-sm"
          style={{
            left: `calc(${pos(price)} - 4px)`,
            background: "rgba(251,191,36,1)",
            boxShadow: "0 0 8px rgba(251,191,36,0.5)",
          }}
          title={`現價 ${price.toFixed(2)}`}
        />
      </div>

      <div className="grid grid-cols-4 gap-2 text-[11px] tabular-nums">
        <div>
          <p className="text-slate-500">低</p>
          <p className="text-slate-300">${fmtNum(low)}</p>
        </div>
        <div>
          <p className="text-slate-500">中</p>
          <p className="text-slate-300">${fmtNum(mid)}</p>
        </div>
        <div>
          <p className="text-slate-500">高</p>
          <p className="text-slate-300">${fmtNum(high)}</p>
        </div>
        <div>
          <p className="text-slate-500">估值偏低區上緣</p>
          <p className="text-emerald-400">${fmtNum(buy)}</p>
        </div>
      </div>

      {v?.notes && <p className="text-[11px] text-slate-500 mt-2">{v.notes}</p>}
    </div>
  );
}

// ── PickDetailDrawer ──────────────────────────────────────────────────────

function PickDetailDrawer({
  pick,
  onClose,
}: {
  pick: PickDoc | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  if (!pick) return null;

  const t = pick.scoring_trace;
  const interp = pick.interpretation;
  const trapStyle = valueTrapStyle(interp?.value_trap_check);

  const sendToChat = () => {
    const code = pick.ticker.replace(".TW", "").replace(".TWO", "");
    const upside = pick.valuation?.implied_upside_mid_pct;
    const prompt = `請深入分析 ${pick.name}（${code}）。
我看到 Screener 給出以下評估：
- 等級：${pick.final_grade}
- 投資觀點：${interp?.narrative || "（無）"}
- 估值中值：${pick.valuation?.fair_value_mid ?? "—"}（上行 ${
      upside != null ? upside.toFixed(1) + "%" : "—"
    }）
- 主要警示：${(interp?.warnings || []).join("、") || "無"}
- 價值陷阱檢查：${trapStyle.label}
請結合最新基本面、技術面、籌碼面，告訴我這個論點目前是否仍成立？`;
    navigate("/chat", { state: { initialMessage: prompt } });
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex"
      onClick={onClose}
      style={{ background: "rgba(0,0,0,0.5)" }}
    >
      <div className="flex-1" />
      <aside
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl h-full overflow-y-auto p-6 md:p-8 animate-fade-up"
        style={{
          background: "var(--bg-surface)",
          borderLeft: "1px solid var(--border)",
        }}
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-baseline gap-2 flex-wrap">
              <h2 className="text-2xl font-semibold text-slate-100">
                {pick.name}
              </h2>
              <span className="text-sm text-slate-500">
                {pick.ticker.replace(".TW", "").replace(".TWO", "")}
              </span>
              <GradeBadge grade={pick.final_grade} />
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {pick.industry} · 產業 #{pick.rank_in_industry}/
              {pick.industry_size}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="關閉"
            className="text-slate-500 hover:text-slate-200 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Narrative */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            投資觀點（AI 解讀）
          </h3>
          <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
            {interp?.narrative || "—"}
          </p>
          {interp?.key_context && interp.key_context.length > 0 && (
            <ul className="mt-3 text-xs text-slate-400 list-disc list-inside space-y-0.5">
              {interp.key_context.map((k, i) => (
                <li key={i}>{k}</li>
              ))}
            </ul>
          )}
        </section>

        {/* Warnings */}
        {interp?.warnings && interp.warnings.length > 0 && (
          <section className="mb-6">
            <h3 className="text-xs uppercase tracking-wider text-amber-400/90 mb-2">
              ⚠ 警示
            </h3>
            <ul className="text-sm text-amber-200/90 list-disc list-inside space-y-1">
              {interp.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </section>
        )}

        {/* Value trap check */}
        <section
          className="mb-6 rounded-xl p-3 text-xs"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-400">價值陷阱檢查</span>
            <span className={`font-semibold ${trapStyle.text}`}>
              {trapStyle.label}
            </span>
          </div>
          {interp?.value_trap_reason && (
            <p className="text-slate-500 mt-1">{interp.value_trap_reason}</p>
          )}
        </section>

        {/* Forward tracking（發布後實績）*/}
        {pick.tracking?.entry_date && (
          <section
            className="mb-6 rounded-xl p-3 text-xs"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-slate-400">
                發布後實績（{pick.tracking.entry_date} 起）
              </span>
              <span className="text-slate-500">
                經過 {pick.tracking.trading_days_elapsed ?? 0} 交易日
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {[
                { label: "目前", v: pick.tracking.return_current },
                { label: "T+5", v: pick.tracking.return_t5 },
                { label: "T+20", v: pick.tracking.return_t20 },
                { label: "T+60", v: pick.tracking.return_t60 },
              ].map(({ label, v }) => (
                <div key={label}>
                  <p className="text-slate-600">{label}</p>
                  <p className={`font-semibold ${pnlColor(v)}`}>
                    {v == null ? "—" : fmtSignedPct(v)}
                  </p>
                </div>
              ))}
            </div>
            {(pick.tracking.max_return != null ||
              pick.tracking.max_drawdown != null) && (
              <p className="text-slate-500 mt-2">
                期間最高 {fmtSignedPct(pick.tracking.max_return)} · 最低{" "}
                {fmtSignedPct(pick.tracking.max_drawdown)}
              </p>
            )}
          </section>
        )}

        {/* Valuation */}
        <section className="mb-6">
          <ValuationBand pick={pick} />
        </section>

        {/* Snapshot */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            數據快照
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
            <SnapshotRow label="PE" value={fmtNum(pick.snapshot.pe)} />
            <SnapshotRow label="PB" value={fmtNum(pick.snapshot.pb)} />
            <SnapshotRow
              label="EPS TTM"
              value={fmtNum(pick.snapshot.eps_ttm)}
            />
            <SnapshotRow
              label="ROE 3Y"
              value={fmtPct(pick.snapshot.roe_3y_avg)}
            />
            <SnapshotRow
              label="營收 3Y CAGR"
              value={fmtPct(pick.snapshot.revenue_cagr_3y)}
            />
            <SnapshotRow
              label="營收 YoY"
              value={fmtPct(pick.snapshot.revenue_yoy_latest)}
            />
            <SnapshotRow
              label="負債比"
              value={fmtPct(pick.snapshot.debt_ratio)}
            />
            <SnapshotRow
              label="流動比"
              value={fmtNum(pick.snapshot.current_ratio)}
            />
            <SnapshotRow
              label="殖利率"
              value={fmtPct(pick.snapshot.dividend_yield)}
            />
            <SnapshotRow
              label="6M 漲幅"
              value={fmtPct(pick.snapshot.return_6m)}
            />
            <SnapshotRow
              label="相對大盤 6M"
              value={fmtPct(pick.snapshot.rel_strength_6m)}
            />
            <SnapshotRow
              label="量比 5/20"
              value={fmtNum(pick.snapshot.volume_ratio_5_20)}
            />
            <SnapshotRow label="RSI 14" value={fmtNum(pick.snapshot.rsi_14)} />
            <SnapshotRow
              label="產業 PE 中位"
              value={fmtNum(pick.snapshot.industry_pe_median)}
            />
            <SnapshotRow
              label="產業 PB 中位"
              value={fmtNum(pick.snapshot.industry_pb_median)}
            />
          </div>
        </section>

        {/* Scoring trace */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-3">
            評分軌跡（規則引擎，零 LLM）
          </h3>

          {t?.rejection_reason && (
            <p className="text-xs text-amber-300/90 mb-3">
              拒絕原因：{t.rejection_reason}
            </p>
          )}
          {(t?.missing_data_count ?? 0) > 0 && (
            <p className="text-[11px] text-slate-500 mb-3">
              資料缺失規則 {t!.missing_data_count} 條（
              {(t!.missing_data_rule_ids || []).join(", ")}）
            </p>
          )}

          <CheckSection
            title="Stage 1 — Universe 過濾"
            checks={t?.stage1_checks ?? []}
            emptyHint="無 Stage 1 紀錄"
          />
          <CheckSection
            title="必要規則 (Must Pass)"
            summary={
              t?.must_pass
                ? `${t.must_pass.passed}/${t.must_pass.total} 通過`
                : undefined
            }
            checks={t?.must_pass?.checks ?? []}
          />
          <CheckSection
            title="加分規則 (Bonus)"
            summary={
              t?.bonus
                ? `${t.bonus.passed}/${t.bonus.required} 達門檻`
                : undefined
            }
            checks={t?.bonus?.checks ?? []}
          />
          <CheckSection
            title="剔除條件 (Disqualifier)"
            summary={
              t?.disqualifier?.triggered.length
                ? `已觸發：${t.disqualifier.triggered.join(", ")}`
                : "未觸發"
            }
            checks={t?.disqualifier?.checks ?? []}
          />
        </section>

        {/* CTA */}
        <button
          onClick={sendToChat}
          className="w-full py-3 text-sm font-semibold text-white rounded-xl transition-transform hover:scale-[1.01]"
          style={{
            background:
              "linear-gradient(135deg, rgba(99,102,241,0.9), rgba(139,92,246,0.85))",
            boxShadow: "0 0 16px rgba(99,102,241,0.3)",
          }}
        >
          💬 丟到 Chat 深入問
        </button>
      </aside>
    </div>
  );
}

function SnapshotRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="flex items-center justify-between rounded-lg px-2.5 py-1.5"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
      }}
    >
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-200 tabular-nums">{value}</span>
    </div>
  );
}

// ── ReportHistory ────────────────────────────────────────────────────────

function ReportHistory({
  reports,
  selectedReportId,
  loading,
  onSelect,
}: {
  reports: ReportSummary[];
  selectedReportId: string | null;
  loading: boolean;
  onSelect: (reportId: string) => void;
}) {
  if (loading) {
    return <p className="text-xs text-slate-500">載入歷史報告…</p>;
  }

  if (reports.length === 0) {
    return null;
  }

  return (
    <section className="mb-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">歷史分析</h2>
          <p className="text-xs text-slate-500 mt-1">
            共 {reports.length} 份{" "}
            {reports[0]?.frequency === "weekly" ? "週報" : "日報"}
          </p>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {reports.map((item, index) => {
          const selected = item.report_id === selectedReportId;
          return (
            <button
              key={item.report_id}
              onClick={() => onSelect(item.report_id)}
              className={`text-left rounded-xl p-3 transition-all hover:border-indigo-500/40 ${
                selected ? "text-white" : "text-slate-400"
              }`}
              style={{
                background: selected
                  ? "linear-gradient(135deg, rgba(99,102,241,0.22), rgba(14,165,233,0.12))"
                  : "var(--card-bg)",
                border: selected
                  ? "1px solid rgba(99,102,241,0.45)"
                  : "1px solid var(--border)",
              }}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-100">
                    {fmtReportDate(item)}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5 font-mono truncate max-w-[11rem]">
                    {item.report_id}
                  </p>
                </div>
                {index === 0 && (
                  <span className="rounded-full border border-emerald-500/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                    最新
                  </span>
                )}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] tabular-nums">
                <div>
                  <p className="text-slate-600">入選</p>
                  <p className="text-slate-300">{item.final_count} 檔</p>
                </div>
                <div>
                  <p className="text-slate-600">產業</p>
                  <p className="text-slate-300">
                    {item.industries_covered.length} 類
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// ── EmailSubscribeToggle ──────────────────────────────────────────────────

function EmailSubscribeToggle() {
  const [enabled, setEnabled] = useState(false);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let active = true;
    getSubscription()
      .then((s) => {
        if (!active) return;
        setEnabled(!!s.enabled);
        setEmail(s.email || "");
      })
      .catch(() => {
        /* 沒訂閱記錄就用預設 */
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const handleToggle = async () => {
    setSaving(true);
    setMsg("");
    try {
      const next = !enabled;
      await updateSubscription({ enabled: next });
      setEnabled(next);
      setMsg(next ? "✓ 已開啟訂閱" : "已停止訂閱");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "更新失敗");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-xs text-slate-500">載入訂閱狀態…</p>;
  }

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <button
        onClick={handleToggle}
        disabled={saving}
        className={`px-4 py-2 text-xs rounded-xl transition-all ${
          enabled ? "text-white" : "text-slate-300 hover:text-white"
        }`}
        style={{
          background: enabled
            ? "linear-gradient(135deg, rgba(16,185,129,0.4), rgba(34,197,94,0.3))"
            : "var(--overlay-bg)",
          border: "1px solid var(--border)",
        }}
      >
        {saving
          ? "更新中…"
          : enabled
            ? "✓ 已訂閱 Email 報告"
            : "📧 訂閱 Email 報告"}
      </button>
      {email && <span className="text-xs text-slate-500">{email}</span>}
      {msg && <span className="text-xs text-slate-400">{msg}</span>}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────

export default function Screener() {
  const [profile, setProfile] = useState<ScreenerProfile>("momentum");
  const [frequency, setFrequency] = useState<ScreenerFrequency>("weekly");
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [activePick, setActivePick] = useState<PickDoc | null>(null);

  const resetForReportList = () => {
    setHistoryLoading(true);
    setLoading(true);
    setError("");
    setReport(null);
    setReports([]);
    setSelectedReportId(null);
    setSelectedIndustry(null);
    setActivePick(null);
  };

  const resetForReportDetail = () => {
    setLoading(true);
    setError("");
    setReport(null);
    setSelectedIndustry(null);
    setActivePick(null);
  };

  const handleProfile = (nextProfile: ScreenerProfile) => {
    if (nextProfile === profile) return;
    resetForReportList();
    setProfile(nextProfile);
  };

  const handleFrequency = (nextFrequency: ScreenerFrequency) => {
    if (nextFrequency === frequency) return;
    resetForReportList();
    setFrequency(nextFrequency);
  };

  const handleReportSelect = (reportId: string) => {
    if (reportId === selectedReportId) return;
    resetForReportDetail();
    setSelectedReportId(reportId);
  };

  useEffect(() => {
    let active = true;
    listReports({ profile, frequency, limit: 24 })
      .then((items) => {
        if (!active) return;
        setReports(items);
        if (items.length === 0) {
          setError("No report found");
          setLoading(false);
          return;
        }
        setSelectedReportId(items[0].report_id);
      })
      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "載入失敗");
        setLoading(false);
      })
      .finally(() => active && setHistoryLoading(false));
    return () => {
      active = false;
    };
  }, [profile, frequency]);

  useEffect(() => {
    if (!selectedReportId) return;
    let active = true;
    getReport(selectedReportId)
      .then((detail) => active && setReport(detail))
      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "載入失敗");
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [selectedReportId]);

  const industries = useMemo(
    () => (report ? Object.keys(report.picks_by_industry).sort() : []),
    [report],
  );
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    if (report) {
      for (const [ind, picks] of Object.entries(report.picks_by_industry)) {
        out[ind] = picks.length;
      }
    }
    return out;
  }, [report]);

  const visiblePicks = useMemo(() => {
    if (!report) return [];
    if (selectedIndustry) {
      return report.picks_by_industry[selectedIndustry] || [];
    }
    return Object.values(report.picks_by_industry).flat();
  }, [report, selectedIndustry]);

  return (
    <div className="px-4 py-6 md:px-10 md:py-10 max-w-6xl mx-auto animate-fade-up">
      <div className="mb-8">
        <h1 className="text-xl md:text-2xl font-semibold text-slate-100">
          🔍 智能選股
        </h1>
        <p className="text-sm text-slate-500 mt-2">
          四階段漏斗 — Universe 篩選 → 規則引擎 → 估值定錨 → AI 解讀
        </p>
      </div>

      <div className="mb-6 space-y-4">
        <ProfileTabs
          profile={profile}
          frequency={frequency}
          onProfile={handleProfile}
          onFrequency={handleFrequency}
        />
        <EmailSubscribeToggle />
      </div>

      <TrackingPanel profile={profile} />

      <ReportHistory
        reports={reports}
        selectedReportId={selectedReportId}
        loading={historyLoading}
        onSelect={handleReportSelect}
      />

      {loading && (
        <div
          className="rounded-2xl p-12 text-center text-sm text-slate-500"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
          }}
        >
          載入報告中…
        </div>
      )}

      {error && !loading && (
        <div
          className="rounded-2xl p-6 text-sm text-amber-300"
          style={{
            background: "rgba(245, 158, 11, 0.1)",
            border: "1px solid rgba(245, 158, 11, 0.3)",
          }}
        >
          {error.includes("404") || error.includes("No report")
            ? `目前還沒有 ${
                profile === "momentum" ? "Momentum" : "Value"
              } ${frequency === "weekly" ? "週報" : "日報"}。`
            : error}
        </div>
      )}

      {report && !loading && (
        <>
          {/* Report meta */}
          <div
            className="rounded-2xl p-4 md:p-5 mb-6 flex flex-wrap gap-4 items-center justify-between"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <div>
              <p className="text-xs text-slate-500">報告日期</p>
              <p className="text-sm text-slate-200">
                {fmtReportDate(report.report)}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">報告編號</p>
              <p className="text-sm text-slate-200 font-mono">
                {report.report.report_id}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">入選 / 涵蓋產業</p>
              <p className="text-sm text-slate-200">
                {report.report.final_count} 檔 ·{" "}
                {report.report.industries_covered.length} 類
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">耗時</p>
              <p className="text-sm text-slate-200">
                {report.report.duration_seconds?.toFixed(0) ?? "—"}s
              </p>
            </div>
          </div>

          {/* Industry chips */}
          <div className="mb-6">
            <IndustryChips
              industries={industries}
              selected={selectedIndustry}
              onSelect={setSelectedIndustry}
              counts={counts}
            />
          </div>

          {/* Picks grid */}
          {visiblePicks.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-12">
              本期該產業沒有符合條件的標的
            </p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {visiblePicks.map((p) => (
                <PickCard
                  key={p.ticker}
                  pick={p}
                  onClick={() => setActivePick(p)}
                />
              ))}
            </div>
          )}
        </>
      )}

      <p className="text-xs text-slate-500 leading-relaxed mt-6">
        ⚠️ 選股報告由規則引擎與 AI 產生，僅供學習與研究用途，不構成投資建議；「估值偏低區」為統計參考，非買進訊號。
      </p>

      <PickDetailDrawer pick={activePick} onClose={() => setActivePick(null)} />
    </div>
  );
}
