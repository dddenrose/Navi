import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getLatestReport,
  getSubscription,
  updateSubscription,
} from "@/lib/api/screener";
import type {
  PickDoc,
  ReportDetail,
  ScreenerFrequency,
  ScreenerProfile,
} from "@/types/screener";

// ── 小工具 ────────────────────────────────────────────────────────────────

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}
function confColor(c: number): string {
  if (c >= 85) return "text-emerald-400 bg-emerald-400/10";
  if (c >= 75) return "text-sky-400 bg-sky-400/10";
  return "text-amber-400 bg-amber-400/10";
}

// ── ProfileTabs ──────────────────────────────────────────────────────────

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

// ── IndustryChips ────────────────────────────────────────────────────────

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

// ── PickCard ─────────────────────────────────────────────────────────────

function PickCard({
  pick,
  onClick,
}: {
  pick: PickDoc;
  onClick: () => void;
}) {
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
            #{pick.rank_in_industry} · {pick.industry}
          </p>
        </div>
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full ${confColor(
            pick.confidence,
          )}`}
        >
          信心 {pick.confidence}
        </span>
      </div>

      <p className="text-xs text-slate-400 line-clamp-3 mb-3 leading-relaxed">
        {pick.thesis}
      </p>

      <div className="grid grid-cols-3 gap-2 text-xs tabular-nums">
        <div>
          <p className="text-slate-600">現價</p>
          <p className="text-slate-200">${fmtNum(pick.snapshot.price)}</p>
        </div>
        <div>
          <p className="text-slate-600">目標</p>
          <p className="text-slate-200">${fmtNum(pick.target_price?.mid)}</p>
        </div>
        <div>
          <p className="text-slate-600">上行</p>
          <p
            className={
              pick.upside_pct >= 0 ? "text-emerald-400" : "text-red-400"
            }
          >
            {pick.upside_pct >= 0 ? "+" : ""}
            {fmtNum(pick.upside_pct, 1)}%
          </p>
        </div>
      </div>
    </button>
  );
}

// ── PickDetailDrawer ─────────────────────────────────────────────────────

function PickDetailDrawer({
  pick,
  onClose,
}: {
  pick: PickDoc | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  if (!pick) return null;

  const sendToChat = () => {
    const code = pick.ticker.replace(".TW", "").replace(".TWO", "");
    const prompt = `請深入分析 ${pick.name}（${code}）。
我看到 Screener 給出以下評估：
- 投資論點：${pick.thesis}
- 信心：${pick.confidence}
- 目標價：${pick.target_price?.mid}（上行 ${pick.upside_pct.toFixed(1)}%）
- 主要風險：${(pick.risks || []).join("、")}
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
            <div className="flex items-baseline gap-2">
              <h2 className="text-2xl font-semibold text-slate-100">
                {pick.name}
              </h2>
              <span className="text-sm text-slate-500">
                {pick.ticker.replace(".TW", "").replace(".TWO", "")}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {pick.industry} · 產業 #{pick.rank_in_industry}
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

        {/* Thesis */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
            投資論點
          </h3>
          <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
            {pick.thesis}
          </p>
        </section>

        {/* Target / SL */}
        <section className="grid grid-cols-3 gap-3 mb-6">
          <div
            className="rounded-xl p-3"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500">目標價區間</p>
            <p className="text-sm text-slate-200 tabular-nums mt-1">
              ${fmtNum(pick.target_price?.low)} ~ $
              {fmtNum(pick.target_price?.high)}
            </p>
          </div>
          <div
            className="rounded-xl p-3"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500">停損</p>
            <p className="text-sm text-red-400 tabular-nums mt-1">
              ${fmtNum(pick.stop_loss)}
            </p>
          </div>
          <div
            className="rounded-xl p-3"
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-xs text-slate-500">風報比</p>
            <p className="text-sm text-slate-200 tabular-nums mt-1">
              {fmtNum(pick.risk_reward_ratio, 2)}
            </p>
          </div>
        </section>

        {/* Snapshot */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
            基本面 / 動能 Snapshot
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
            <Row label="PE" value={fmtNum(pick.snapshot.pe)} />
            <Row label="PB" value={fmtNum(pick.snapshot.pb)} />
            <Row label="ROE" value={fmtPct(pick.snapshot.roe)} />
            <Row label="殖利率" value={fmtPct(pick.snapshot.dividend_yield)} />
            <Row label="毛利率" value={fmtPct(pick.snapshot.profit_margin)} />
            <Row label="營收 YoY" value={fmtPct(pick.snapshot.revenue_growth)} />
            <Row label="3M 漲幅" value={fmtPct(pick.snapshot.return_3m)} />
            <Row label="6M 漲幅" value={fmtPct(pick.snapshot.return_6m)} />
            <Row
              label="相對大盤"
              value={fmtPct(pick.snapshot.rel_strength_3m)}
            />
          </div>
        </section>

        {/* Factor scores */}
        <section className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
            因子分數
          </h3>
          <div className="space-y-2">
            {Object.entries(pick.factor_scores).map(([k, v]) => (
              <div key={k} className="flex items-center gap-3">
                <span className="text-xs text-slate-500 w-20">{k}</span>
                <div
                  className="flex-1 h-2 rounded-full overflow-hidden"
                  style={{ background: "var(--overlay-bg)" }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.max(0, Math.min(100, v))}%`,
                      background:
                        "linear-gradient(90deg, rgba(99,102,241,0.6), rgba(139,92,246,0.8))",
                    }}
                  />
                </div>
                <span className="text-xs tabular-nums text-slate-300 w-10 text-right">
                  {v.toFixed(0)}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Risks */}
        {pick.risks?.length > 0 && (
          <section className="mb-6">
            <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
              主要風險
            </h3>
            <ul className="text-sm text-slate-300 list-disc list-inside space-y-1">
              {pick.risks.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </section>
        )}

        {/* KB citations */}
        {pick.kb_citations?.length > 0 && (
          <section className="mb-6">
            <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
              知識庫引用
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {pick.kb_citations.map((c, i) => (
                <span
                  key={i}
                  className="text-xs px-2 py-0.5 rounded-full text-slate-400"
                  style={{
                    background: "var(--overlay-bg)",
                    border: "1px solid var(--border)",
                  }}
                >
                  {c}
                </span>
              ))}
            </div>
          </section>
        )}

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

function Row({ label, value }: { label: string; value: string }) {
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

// ── EmailSubscribeToggle ─────────────────────────────────────────────────

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
      setMsg(next ? "✓ 已開啟訂閱，週日晚上會收到報告" : "已停止訂閱");
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
          enabled
            ? "text-white"
            : "text-slate-300 hover:text-white"
        }`}
        style={{
          background: enabled
            ? "linear-gradient(135deg, rgba(16,185,129,0.4), rgba(34,197,94,0.3))"
            : "var(--overlay-bg)",
          border: "1px solid var(--border)",
        }}
      >
        {saving ? "更新中…" : enabled ? "✓ 已訂閱 Email 週報" : "📧 訂閱 Email 週報"}
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
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [activePick, setActivePick] = useState<PickDoc | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setReport(null);
    setSelectedIndustry(null);
    getLatestReport(profile, frequency)
      .then((r) => active && setReport(r))
      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "載入失敗");
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [profile, frequency]);

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
          每週自動跑三階段漏斗 — 量化粗篩 → 多因子打分 → AI 深度評估
        </p>
      </div>

      <div className="mb-6 space-y-4">
        <ProfileTabs
          profile={profile}
          frequency={frequency}
          onProfile={setProfile}
          onFrequency={setFrequency}
        />
        <EmailSubscribeToggle />
      </div>

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
            ? `目前還沒有 ${profile === "momentum" ? "Momentum" : "Value"} ${
                frequency === "weekly" ? "週報" : "日報"
              }。週報於每週日 20:00 (Asia/Taipei) 自動產出。`
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

      <PickDetailDrawer
        pick={activePick}
        onClose={() => setActivePick(null)}
      />
    </div>
  );
}
