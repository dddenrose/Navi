import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check,
  ChevronDown,
  ClipboardList,
  FlaskConical,
  Gem,
  Info,
  Mail,
  MessageSquare,
  Rocket,
  TrendingUp,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  useScreenerReport,
  useScreenerReports,
  useScreenerSubscription,
  useTrackingSummary,
  useUpdateScreenerSubscription,
} from "@/lib/queries/screener";
import type {
  FinalGrade,
  PickDoc,
  ReportSummary,
  RuleCheck,
  ScreenerFrequency,
  ScreenerProfile,
  StrategyEvidence,
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
  if (v == null || Number.isNaN(v)) return "text-ink-muted";
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
        text: "text-ink-muted",
        bg: "bg-[var(--surface-2)] border-line",
        label: String(grade || "—"),
      };
  }
}

function valueTrapStyle(c: ValueTrapCheck | undefined): { text: string; label: string } {
  switch (c) {
    case "no_concern":
      return { text: "text-emerald-400", label: "已檢查・無重大疑慮" };
    case "watch":
      return { text: "text-amber-400", label: "觀察" };
    case "warning":
      return { text: "text-red-400", label: "疑似價值陷阱" };
    case "not_applicable":
      // 「沒有檢查」與「已檢查無虞」是兩回事 —— 中性呈現，不給綠色
      return { text: "text-ink-muted", label: "不適用（本策略未檢查）" };
    default:
      // 未知列舉值以警示色呈現（寧可誤警不可漏警）；無值維持中性
      return c
        ? { text: "text-red-400", label: String(c) }
        : { text: "text-ink-muted", label: "—" };
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
  const profiles: { key: ScreenerProfile; label: string; Icon: LucideIcon }[] = [
    { key: "momentum", label: "Momentum Rider", Icon: Rocket },
    { key: "value", label: "Value Hunter", Icon: Gem },
  ];
  const freqs: { key: ScreenerFrequency; label: string }[] = [
    { key: "weekly", label: "週報" },
    { key: "daily", label: "日報" },
  ];
  return (
    <div className="flex flex-wrap gap-3 items-center">
      <div className="inline-flex p-1 rounded-xl bg-[var(--surface-1)]">
        {profiles.map((p) => (
          <button
            key={p.key}
            onClick={() => onProfile(p.key)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1.5 ${
              profile === p.key
                ? "text-ink-strong bg-[var(--accent-soft)]"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            <p.Icon size={13} aria-hidden="true" />
            {p.label}
          </button>
        ))}
      </div>
      <div className="inline-flex p-1 rounded-xl bg-[var(--surface-1)]">
        {freqs.map((f) => (
          <button
            key={f.key}
            onClick={() => onFrequency(f.key)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
              frequency === f.key
                ? "text-ink-strong bg-[var(--accent-soft)]"
                : "text-ink-muted hover:text-ink"
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
        className={`px-3 py-1 text-xs rounded-full transition-colors border ${
          selected === null
            ? "text-ink-strong bg-[var(--accent-soft)] border-transparent"
            : "text-ink-muted hover:text-ink bg-[var(--surface-1)] border-[var(--border-default)]"
        }`}
      >
        全部 ({Object.values(counts).reduce((a, b) => a + b, 0)})
      </button>
      {industries.map((ind) => (
        <button
          key={ind}
          onClick={() => onSelect(ind)}
          className={`px-3 py-1 text-xs rounded-full transition-colors border ${
            selected === ind
              ? "text-ink-strong bg-[var(--accent-soft)] border-transparent"
              : "text-ink-muted hover:text-ink bg-[var(--surface-1)] border-[var(--border-default)]"
          }`}
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
    <button onClick={onClick} className="card card-hover text-left p-4 md:p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-ink-strong">
              {pick.name || pick.ticker}
            </h3>
            <span className="text-xs text-ink-muted">
              {pick.ticker.replace(".TW", "").replace(".TWO", "")}
            </span>
          </div>
          <p className="text-xs text-ink-muted mt-0.5">
            {pick.rank_overall ? `全市場 #${pick.rank_overall} · ` : ""}
            {pick.industry}（同業評估 {pick.industry_size} 檔中第{" "}
            {pick.rank_in_industry}）
          </p>
        </div>
        <GradeBadge grade={pick.final_grade} />
      </div>

      <p className="text-xs text-ink-secondary line-clamp-3 mb-1 leading-relaxed">
        {pick.interpretation?.narrative || "—"}
      </p>
      <p className="text-[10px] text-ink-faint mb-3">AI 生成，業務敘述未經查證</p>

      <div className="grid grid-cols-3 gap-2 text-xs tabular-nums">
        <div>
          <p className="text-ink-faint">現價</p>
          <p className="text-ink">${fmtNum(pick.snapshot.price)}</p>
        </div>
        <div>
          <p className="text-ink-faint">同業推算中值</p>
          <p className="text-ink">${fmtNum(v?.fair_value_mid)}</p>
        </div>
        <div>
          {/* 刻意不用「上行/upside」報酬語言：此數字是相對同業的估值差
              （與入選規則同一把尺，非預期報酬），預測力由 tracking 檢驗 */}
          <p className="text-ink-faint">同業估值差</p>
          <p
            className={
              upside == null
                ? "text-ink-muted"
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
        <div className="mt-3 pt-3 border-t border-line-subtle flex items-center justify-between text-[11px]">
          <span className="text-ink-muted">價值陷阱檢查</span>
          <span className={trapStyle.text}>{trapStyle.label}</span>
        </div>
      )}
    </button>
  );
}

// ── EvidenceBanner（策略證據揭露 — evidence gate）─────────────────────────

function EvidenceBanner({ evidence }: { evidence: StrategyEvidence | null | undefined }) {
  const [expanded, setExpanded] = useState(false);
  if (!evidence) return null;

  const isBacktested = evidence.status === "backtested";
  const m13 = evidence.metrics?.hold_13w;
  const m26 = evidence.metrics?.hold_26w;

  return (
    <div
      className="rounded-card p-4 mb-6 text-xs leading-relaxed"
      style={{
        background: isBacktested
          ? "rgba(245, 158, 11, 0.08)"
          : "rgba(148, 163, 184, 0.08)",
        border: isBacktested
          ? "1px solid rgba(245, 158, 11, 0.3)"
          : "1px solid rgba(148, 163, 184, 0.3)",
      }}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-[16rem]">
          <p
            className={`font-semibold mb-1 flex items-center gap-1.5 ${
              isBacktested ? "text-amber-300" : "text-ink"
            }`}
          >
            <ClipboardList size={14} aria-hidden="true" />
            策略證據：{evidence.headline}
          </p>
          {isBacktested && m13 && (
            <p className="text-ink-secondary">
              回測 {evidence.backtest_period}・持有 13 週：年化{" "}
              <span className="text-ink">
                {fmtSignedPct(m13.strategy_cagr)}
              </span>{" "}
              vs 大盤 {fmtSignedPct(m13.benchmark_cagr)}（超額{" "}
              <span className={pnlColor(m13.excess_cagr)}>
                {fmtSignedPct(m13.excess_cagr)}
              </span>
              ）
              {m26 && (
                <>
                  ・持有 26 週超額{" "}
                  <span className={pnlColor(m26.excess_cagr)}>
                    {fmtSignedPct(m26.excess_cagr)}
                  </span>
                </>
              )}
              ・最大回撤 {fmtSignedPct(m13.max_drawdown)}
            </p>
          )}
          {!isBacktested && evidence.caveats?.[0] && (
            <p className="text-ink-secondary">{evidence.caveats[0]}</p>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-ink-secondary hover:text-ink whitespace-nowrap flex items-center gap-1"
        >
          {expanded ? "收合" : "完整揭露"}
          <ChevronDown
            size={13}
            className={`transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
      </div>
      {expanded && (
        <div className="mt-3 pt-3 border-t border-line-subtle">
          {evidence.method && (
            <p className="text-ink-muted mb-2">回測方法：{evidence.method}</p>
          )}
          <ul className="list-disc list-inside space-y-1 text-ink-secondary">
            {evidence.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── TrackingPanel（推薦實績追蹤）───────────────────────────────────────────

const TRACKING_HORIZONS: { key: string; label: string; primary?: boolean }[] = [
  { key: "t5", label: "T+5" },
  { key: "t20", label: "T+20" },
  { key: "t60", label: "T+60" },
  { key: "t120", label: "T+120", primary: true }, // ≈ 6 個月，主要成功指標
];

const MIN_RELIABLE_SAMPLE = 30;

function TrackingPanel({ profile }: { profile: ScreenerProfile }) {
  const summary = useTrackingSummary(profile).data ?? null;

  if (!summary || !summary.pick_events) return null;

  return (
    <div className="card p-4 md:p-5 mb-6">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <h3 className="text-sm font-medium text-ink flex items-center gap-1.5">
          <TrendingUp size={14} aria-hidden="true" />
          推薦實績追蹤
        </h3>
        <span className="text-[11px] text-ink-muted">
          {summary.pick_events} 次推薦事件 · {summary.report_count} 份報告
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {TRACKING_HORIZONS.map(({ key, label, primary }) => {
          const h = summary.horizons?.[key];
          if (!h || h.n === 0) {
            return (
              <div key={key} className="rounded-field p-3 bg-[var(--surface-1)]">
                <p className="text-[11px] text-ink-muted mb-1">
                  {label} 交易日{primary ? "・主指標" : ""}
                </p>
                <p className="text-sm text-ink-faint">樣本累積中…</p>
              </div>
            );
          }
          const lowSample = h.n < MIN_RELIABLE_SAMPLE;
          return (
            <div
              key={key}
              className="rounded-field p-3 bg-[var(--surface-1)]"
              style={{
                border: primary ? "1px solid var(--focus-ring)" : undefined,
              }}
            >
              <p className="text-[11px] text-ink-muted mb-1">
                {label} 交易日{primary ? "・主指標" : ""} · n={h.n}
              </p>
              <p
                className={`text-lg font-semibold ${
                  lowSample ? "text-ink-secondary" : pnlColor(h.avg_return)
                }`}
              >
                {fmtSignedPct(h.avg_return)}
              </p>
              <p className="text-[11px] text-ink-muted mt-1">
                勝率 {fmtPct(h.win_rate, 0)}
                {h.avg_excess != null && (
                  <>
                    {" "}· 超額大盤{" "}
                    <span
                      className={lowSample ? "text-ink-muted" : pnlColor(h.avg_excess)}
                    >
                      {fmtSignedPct(h.avg_excess)}
                    </span>
                  </>
                )}
              </p>
              {lowSample && (
                <p className="text-[10px] text-amber-400/80 mt-1">
                  樣本 &lt; {MIN_RELIABLE_SAMPLE}，勿據此下結論
                </p>
              )}
            </div>
          );
        })}
      </div>
      <UpsideValidationNote summary={summary} />
      {summary.methodology && (
        <p className="text-[11px] text-ink-faint mt-3 leading-relaxed">
          {summary.methodology}
        </p>
      )}
    </div>
  );
}

function UpsideValidationNote({ summary }: { summary: TrackingSummary }) {
  // 「上行空間」欄位的誠實檢驗：與實際報酬的相關性。樣本夠才顯示。
  const v = summary.upside_validation?.t120 ?? summary.upside_validation?.t60;
  if (!v || v.n < MIN_RELIABLE_SAMPLE || v.pearson_r == null) return null;
  const weak = Math.abs(v.pearson_r) < 0.1;
  return (
    <p className="text-[11px] mt-3 leading-relaxed text-ink-muted flex items-start gap-1.5">
      <FlaskConical size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <span>
        「上行空間」預測力檢驗（n={v.n}）：與實際報酬相關係數 r=
        {v.pearson_r.toFixed(2)}
        {weak && (
          <span className="text-amber-400/90">
            {" "}
            — 目前看不出預測力，該數字請當「相對同業折價」而非預期報酬
          </span>
        )}
      </span>
    </p>
  );
}

// ── Detail components ──────────────────────────────────────────────────────

function RuleRow({ c }: { c: RuleCheck }) {
  const Icon = c.passed ? Check : X;
  const iconColor = c.passed
    ? "text-emerald-400"
    : c.severity === "critical"
      ? "text-red-400"
      : "text-amber-400";
  // 優先用結構化欄位；舊報告無此欄位時 fallback 字串前綴
  const isMissing = c.missing ?? String(c.actual ?? "").startsWith("資料不足");
  const isSoftWarning = !c.passed && c.severity === "warning";
  return (
    <div className="card flex items-start gap-3 py-2 px-3 rounded-chip text-xs">
      <Icon
        size={14}
        className={`${iconColor} mt-0.5 flex-shrink-0`}
        aria-hidden="true"
      />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="font-semibold text-ink">{c.name}</span>
          <span className="text-[10px] text-ink-muted font-mono">
            {c.rule_id}
          </span>
          {isSoftWarning && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-amber-500/40 bg-amber-400/10 text-amber-300">
              警示・不影響入選
            </span>
          )}
        </div>
        <p className="text-ink-muted mt-0.5">{c.rule}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px]">
          <span className={isMissing ? "text-amber-400/90" : "text-ink"}>
            實際：{fmtRule(c.actual)}
          </span>
          {c.reference != null && c.reference !== "" && (
            <span className="text-ink-muted">門檻：{fmtRule(c.reference)}</span>
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
        <h4 className="text-xs uppercase tracking-wider text-ink-secondary">
          {title}
        </h4>
        {summary && (
          <span className="text-[11px] text-ink-muted">{summary}</span>
        )}
      </div>
      {checks.length === 0 ? (
        <p className="text-[11px] text-ink-faint italic">{emptyHint || "—"}</p>
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
    return <div className="card p-4 text-xs text-ink-muted">估值資料不足</div>;
  }

  // 把 low/mid/high/price/buy 投影到 0~100% 軸
  const min = Math.min(low, price) * 0.95;
  const max = Math.max(high, price) * 1.05;
  const span = max - min || 1;
  const pos = (val: number) =>
    `${Math.max(0, Math.min(100, ((val - min) / span) * 100))}%`;

  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="text-xs uppercase tracking-wider text-ink-secondary">
          估值區間（{v?.method || "—"}）
        </h4>
        <span
          className={`text-xs tabular-nums ${
            (v?.implied_upside_mid_pct ?? 0) >= 0
              ? "text-emerald-400"
              : "text-red-400"
          }`}
        >
          同業估值差 {fmtSigned(v?.implied_upside_mid_pct)}
        </span>
      </div>

      {/* 帶狀圖 */}
      <div className="relative h-9 mb-2">
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-[var(--surface-1)]" />
        {/* fair value band low~high */}
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full"
          style={{
            left: pos(low),
            width: `calc(${pos(high)} - ${pos(low)})`,
            background: "color-mix(in srgb, var(--accent) 55%, transparent)",
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
          }}
          title={`現價 ${price.toFixed(2)}`}
        />
      </div>

      <div className="grid grid-cols-4 gap-2 text-[11px] tabular-nums">
        <div>
          <p className="text-ink-muted">低</p>
          <p className="text-ink">${fmtNum(low)}</p>
        </div>
        <div>
          <p className="text-ink-muted">中</p>
          <p className="text-ink">${fmtNum(mid)}</p>
        </div>
        <div>
          <p className="text-ink-muted">高</p>
          <p className="text-ink">${fmtNum(high)}</p>
        </div>
        <div>
          <p className="text-ink-muted">估值偏低區上緣</p>
          <p className="text-emerald-400">${fmtNum(buy)}</p>
        </div>
      </div>

      <p className="text-[11px] text-ink-faint mt-2">
        以同業 PE 區間推算（
        {pick.snapshot.industry_anchor || "產業中位"}
        ），為相對估值參考、非目標價；「同業估值差」非預期報酬。
      </p>
      {v?.notes && (
        <p className="text-[11px] text-ink-muted mt-1">
          {Array.isArray(v.notes) ? v.notes.join("；") : v.notes}
        </p>
      )}
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
- 同業推算估值中值：${pick.valuation?.fair_value_mid ?? "—"}（相對同業估值差 ${
      upside != null ? upside.toFixed(1) + "%" : "—"
    }，非預期報酬）
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
        className="w-full max-w-xl h-full overflow-y-auto p-6 md:p-8 animate-fade-up bg-surface border-l border-line-subtle"
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-baseline gap-2 flex-wrap">
              <h2 className="text-2xl font-semibold text-ink-strong">
                {pick.name}
              </h2>
              <span className="text-sm text-ink-muted">
                {pick.ticker.replace(".TW", "").replace(".TWO", "")}
              </span>
              <GradeBadge grade={pick.final_grade} />
            </div>
            <p className="text-xs text-ink-muted mt-1">
              {pick.industry} · 產業 #{pick.rank_in_industry}/
              {pick.industry_size}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="關閉"
            className="text-ink-muted hover:text-ink"
          >
            <X size={22} aria-hidden="true" />
          </button>
        </div>

        {/* Narrative */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-ink-secondary mb-2">
            投資觀點（AI 解讀）
          </h3>
          <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">
            {interp?.narrative || "—"}
          </p>
          {interp?.key_context && interp.key_context.length > 0 && (
            <ul className="mt-3 text-xs text-ink-secondary list-disc list-inside space-y-0.5">
              {interp.key_context.map((k, i) => (
                <li key={i}>{k}</li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[10px] text-ink-muted">
            AI 生成內容，業務敘述未經查證，不構成投資建議
          </p>
        </section>

        {/* Warnings */}
        {interp?.warnings && interp.warnings.length > 0 && (
          <section className="mb-6">
            <h3 className="text-xs uppercase tracking-wider text-warn mb-2 flex items-center gap-1.5">
              <TriangleAlert size={14} aria-hidden="true" />
              警示
            </h3>
            <ul className="text-sm text-amber-200/90 list-disc list-inside space-y-1">
              {interp.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </section>
        )}

        {/* Value trap check */}
        <section className="card mb-6 p-3 text-xs">
          <div className="flex items-center justify-between mb-1">
            <span className="text-ink-secondary">價值陷阱檢查</span>
            <span className={`font-semibold ${trapStyle.text}`}>
              {trapStyle.label}
            </span>
          </div>
          {interp?.value_trap_reason && (
            <p className="text-ink-muted mt-1">{interp.value_trap_reason}</p>
          )}
        </section>

        {/* Forward tracking（發布後實績）*/}
        {pick.tracking?.entry_date && (
          <section className="card mb-6 p-3 text-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-ink-secondary">
                發布後實績（{pick.tracking.entry_date} 起）
              </span>
              <span className="text-ink-muted">
                經過 {pick.tracking.trading_days_elapsed ?? 0} 交易日
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {[
                { label: "目前", v: pick.tracking.return_current },
                { label: "T+5", v: pick.tracking.return_t5 },
                { label: "T+20", v: pick.tracking.return_t20 },
                { label: "T+60", v: pick.tracking.return_t60 },
                { label: "T+120", v: pick.tracking.return_t120 },
              ].map(({ label, v }) => (
                <div key={label}>
                  <p className="text-ink-faint">{label}</p>
                  <p className={`font-semibold ${pnlColor(v)}`}>
                    {v == null ? "—" : fmtSignedPct(v)}
                  </p>
                </div>
              ))}
            </div>
            {(pick.tracking.max_return != null ||
              pick.tracking.max_drawdown != null) && (
              <p className="text-ink-muted mt-2">
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
          <h3 className="text-xs uppercase tracking-wider text-ink-secondary mb-2">
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
          <h3 className="text-xs uppercase tracking-wider text-ink-secondary mb-3">
            評分軌跡（規則引擎，零 LLM）
          </h3>

          {t?.rejection_reason && (
            <p className="text-xs text-amber-300/90 mb-3">
              拒絕原因：{t.rejection_reason}
            </p>
          )}
          {(t?.missing_data_count ?? 0) > 0 && (
            <p className="text-[11px] text-ink-muted mb-3">
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
            title="剔除條件與風險警示 (Disqualifier)"
            summary={(() => {
              const checks = t?.disqualifier?.checks ?? [];
              const hard = t?.disqualifier?.triggered.length ?? 0;
              const soft = checks.filter(
                (c) => !c.passed && c.severity === "warning",
              ).length;
              const parts: string[] = [];
              parts.push(
                hard
                  ? `硬剔除已觸發：${t!.disqualifier.triggered.join(", ")}`
                  : "硬剔除未觸發",
              );
              if (soft) parts.push(`軟警示 ${soft} 條（不影響入選）`);
              return parts.join(" · ");
            })()}
            checks={t?.disqualifier?.checks ?? []}
          />
        </section>

        {/* CTA */}
        <button
          onClick={sendToChat}
          className="btn btn-primary w-full justify-center py-3 text-sm"
        >
          <MessageSquare size={15} aria-hidden="true" />
          丟到 Chat 深入問
        </button>
      </aside>
    </div>
  );
}

function SnapshotRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="card flex items-center justify-between px-2.5 py-1.5">
      <span className="text-ink-muted">{label}</span>
      <span className="text-ink tabular-nums">{value}</span>
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
    return <p className="text-xs text-ink-muted">載入歷史報告…</p>;
  }

  if (reports.length === 0) {
    return null;
  }

  return (
    <section className="mb-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">歷史分析</h2>
          <p className="text-xs text-ink-muted mt-1">
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
              className={`text-left rounded-field p-3 transition-all border ${
                selected
                  ? "text-ink-strong bg-[var(--accent-soft)] border-[var(--focus-ring)]"
                  : "text-ink-secondary bg-[var(--surface-1)] border-line-subtle card-hover"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-ink-strong">
                    {fmtReportDate(item)}
                  </p>
                  <p className="text-[11px] text-ink-muted mt-0.5 font-mono truncate max-w-[11rem]">
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
                  <p className="text-ink-faint">入選</p>
                  <p className="text-ink">{item.final_count} 檔</p>
                </div>
                <div>
                  <p className="text-ink-faint">產業</p>
                  <p className="text-ink">
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
  const { data: subscription, isLoading } = useScreenerSubscription();
  const updateSub = useUpdateScreenerSubscription();
  const [msg, setMsg] = useState("");

  // 查無訂閱記錄（data 為 null）時套用預設：未訂閱、無 email
  const enabled = !!subscription?.enabled;
  const email = subscription?.email || "";
  const saving = updateSub.isPending;

  const handleToggle = async () => {
    setMsg("");
    try {
      const next = !enabled;
      // 成功後由 mutation 把回傳值寫回快取，enabled 自然跟著翻
      await updateSub.mutateAsync({ enabled: next });
      setMsg(next ? "已開啟訂閱" : "已停止訂閱");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "更新失敗");
    }
  };

  if (isLoading) {
    return <p className="text-xs text-ink-muted">載入訂閱狀態…</p>;
  }

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <button
        onClick={handleToggle}
        disabled={saving}
        className={`px-4 py-2 text-xs rounded-field transition-all border flex items-center gap-1.5 ${
          enabled
            ? "text-emerald-300 bg-emerald-400/15 border-emerald-500/40"
            : "text-ink hover:text-ink-strong bg-[var(--surface-1)] border-line-subtle"
        }`}
      >
        {saving ? (
          "更新中…"
        ) : enabled ? (
          <>
            <Check size={13} aria-hidden="true" />
            已訂閱 Email 報告
          </>
        ) : (
          <>
            <Mail size={13} aria-hidden="true" />
            訂閱 Email 報告
          </>
        )}
      </button>
      {email && <span className="text-xs text-ink-muted">{email}</span>}
      {msg && <span className="text-xs text-ink-secondary">{msg}</span>}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────

export default function Screener() {
  const [profile, setProfile] = useState<ScreenerProfile>("momentum");
  const [frequency, setFrequency] = useState<ScreenerFrequency>("weekly");
  // 使用者手動選的報告；null＝跟隨清單第一份（最新一期）
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [activePick, setActivePick] = useState<PickDoc | null>(null);

  const reportsQuery = useScreenerReports(profile, frequency);
  const reports = reportsQuery.data ?? [];
  // 「自動選第一份」從 effect 改為推導：清單換了、使用者又沒指定，
  // 自然就落回新清單的第一份，不需要一個 effect 去追著 setState。
  const activeReportId = selectedReportId ?? reports[0]?.report_id ?? null;
  const reportQuery = useScreenerReport(activeReportId);
  const report = reportQuery.data ?? null;

  // isLoading（非 isPending）：query 停用或快取命中時為 false，
  // 清單為空而沒有報告可載時才不會卡在「載入中」。
  const historyLoading = reportsQuery.isLoading;
  // 清單還在載入時報告區也算載入中：此時 activeReportId 還是 null、
  // 細節 query 尚未啟用，只看 reportQuery 會讓報告區空白一段時間
  // （原本 resetForReportList 會把兩個 loading 一起設為 true）。
  const loading = reportsQuery.isLoading || reportQuery.isLoading;
  const error =
    reportsQuery.error || reportQuery.error
      ? ((reportsQuery.error ?? reportQuery.error) as Error).message ||
        "載入失敗"
      : !reportsQuery.isLoading && reports.length === 0
        ? "No report found"
        : "";

  // 換 profile／frequency 或換報告時，只需要清掉使用者的挑選狀態；
  // 資料本身隨 queryKey 變動自動切換，不必手動清空。
  const resetForReportList = () => {
    setSelectedReportId(null);
    setSelectedIndustry(null);
    setActivePick(null);
  };

  const resetForReportDetail = () => {
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
    // 比對 activeReportId：selectedReportId 為 null 時代表「跟隨最新一期」，
    // 此時再點最新那一份不該當成換報告。
    if (reportId === activeReportId) return;
    resetForReportDetail();
    setSelectedReportId(reportId);
  };

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
        <h1 className="text-xl md:text-2xl font-semibold text-ink-strong">
          智能選股
        </h1>
        <p className="text-sm text-ink-muted mt-2">
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

      <TrackingPanel key={profile} profile={profile} />

      <ReportHistory
        reports={reports}
        selectedReportId={activeReportId}
        loading={historyLoading}
        onSelect={handleReportSelect}
      />

      {loading && (
        <div className="card p-12 text-center text-sm text-ink-muted">
          載入報告中…
        </div>
      )}

      {error && !loading && (
        <div
          className="rounded-card p-6 text-sm text-amber-300"
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
          {/* Evidence gate：策略證據常駐揭露 */}
          <EvidenceBanner evidence={report.report.evidence} />

          {profile === "value" && (
            <p className="text-[11px] text-ink-muted mb-4 leading-relaxed flex items-start gap-1.5">
              <Info size={13} className="shrink-0 mt-0.5" aria-hidden="true" />
              <span>
                Value Hunter 的財務安全規則（負債比 &lt;
                60%、流動比）不適用於金融保險業的負債結構，金融股不會出現在本名單
                —— 這是規則設計的限制，不代表金融股本期不值得投資。
              </span>
            </p>
          )}

          {/* Report meta */}
          <div className="card p-4 md:p-5 mb-6 flex flex-wrap gap-4 items-center justify-between">
            <div>
              <p className="text-xs text-ink-muted">報告日期</p>
              <p className="text-sm text-ink">
                {fmtReportDate(report.report)}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">報告編號</p>
              <p className="text-sm text-ink font-mono">
                {report.report.report_id}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">入選 / 涵蓋產業</p>
              <p className="text-sm text-ink">
                {report.report.final_count} 檔 ·{" "}
                {report.report.industries_covered.length} 類
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">耗時</p>
              <p className="text-sm text-ink">
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
            <p className="text-sm text-ink-muted text-center py-12">
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

      <p className="text-xs text-ink-muted leading-relaxed mt-6 flex items-start gap-1.5">
        <TriangleAlert
          size={14}
          className="text-warn shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <span>
          選股報告由規則引擎與 AI 產生，僅供學習與研究用途，不構成投資建議；「估值偏低區」為統計參考，非買進訊號。
        </span>
      </p>

      <PickDetailDrawer pick={activePick} onClose={() => setActivePick(null)} />
    </div>
  );
}
