"""Screener Tool — Agent 可查詢 Navi 智能選股報告（排程產出的名單與入選理由）."""

import logging
import re
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from config import settings
from services import feature_access_service
from services.screener.evidence import get_evidence
from services.screener.reports import find_latest_report, load_pick_docs
from tools.runtime import user_id_from

logger = logging.getLogger(__name__)

PROFILE_LABELS = {"momentum": "動能策略", "value": "價值策略"}
_FREQUENCY_LABELS = {"weekly": "週報", "daily": "日報"}
_ACCESS_REASON_MESSAGES = {
    "account_suspended": "帳號已被停用，無法查詢智能選股。",
    "feature_disabled": "智能選股目前已被管理員暫停。",
}
# 名單沒給出來時，模型很容易自己編一份；明確叫它不要
_NO_LIST_HINT = "請直接告知使用者，不要自行列出任何選股名單。"


def _access_denied_message(user_id: str) -> str | None:
    """與網頁 /api/screener 共用同一份功能權限設定；None 表示可以查."""
    if not settings.auth_required:
        return None
    if not user_id:
        return "智能選股需要登入後才能查詢。"
    result = feature_access_service.check_feature_access("screener", user_id)
    if result.allowed:
        return None
    if result.reason in _ACCESS_REASON_MESSAGES:
        return _ACCESS_REASON_MESSAGES[result.reason]
    tiers = "、".join(result.allowed_tiers)
    return f"智能選股目前只開放給 {tiers} 方案，這位使用者是 {result.tier} 方案。"


def _code(ticker: str) -> str:
    return ticker.split(".")[0]


def _stock_label(pick: dict[str, Any]) -> str:
    """名稱加代號，例如 建準（2421）."""
    return f"{pick.get('name', '')}（{_code(str(pick.get('ticker', '')))}）"


def _report_label(report: dict[str, Any]) -> str:
    """report_id 轉成日期加頻率，例如 20261011-weekly-value → 2026-10-11 週報."""
    report_id = str(report.get("report_id", ""))
    raw_date = report_id[:8]
    date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if raw_date.isdigit() else report_id
    frequency = _FREQUENCY_LABELS.get(str(report.get("frequency", "")), "")
    return " ".join(part for part in (date, frequency) if part)


def _report_heading(report: dict[str, Any], profile: str) -> str:
    return f"📋 Navi 智能選股｜{PROFILE_LABELS[profile]}（{_report_label(report)}）"


def _passed_rule_names(pick: dict[str, Any], section: str) -> list[str]:
    checks = ((pick.get("scoring_trace") or {}).get(section) or {}).get("checks") or []
    return [str(c.get("name", "")) for c in checks if c.get("passed") and c.get("name")]


def _one_line_reason(pick: dict[str, Any]) -> str:
    key_context = (pick.get("interpretation") or {}).get("key_context") or []
    if key_context:
        return str(key_context[0])
    # AI 解讀失敗的檔次沒有 key_context，退回規則名稱
    rules = _passed_rule_names(pick, "must_pass")
    return f"通過規則：{'、'.join(rules)}" if rules else ""


def _evidence_block(profile: str) -> str:
    evidence = get_evidence(profile)
    lines = [f"🔎 策略證據：{evidence['headline']}"]
    hold = (evidence.get("metrics") or {}).get("hold_13w")
    if hold:
        lines.append(
            f"・回測 {evidence['backtest_period']}，持有 13 週："
            f"策略年化 {hold['strategy_cagr']:.1%}、大盤年化 {hold['benchmark_cagr']:.1%}"
            f"、最大回撤 {hold['max_drawdown']:.1%}"
        )
    lines.extend(f"・{caveat}" for caveat in evidence.get("caveats") or [])
    return "\n".join(lines)


def _format_list(report: dict[str, Any], profile: str, picks: list[dict[str, Any]]) -> str:
    lines = [f"{_report_heading(report, profile)}，共 {len(picks)} 檔"]
    for pick in picks:
        line = (
            f"{pick.get('rank_overall')}. {_stock_label(pick)}"
            f"{pick.get('industry', '')}｜{pick.get('final_grade', '')}"
        )
        reason = _one_line_reason(pick)
        lines.append(f"{line}｜{reason}" if reason else line)
    lines.append("這是依固定規則篩選的名單，不是買進建議。")
    lines.append(_evidence_block(profile))
    return "\n".join(lines)


def _format_rules(pick: dict[str, Any]) -> list[str]:
    trace = pick.get("scoring_trace") or {}
    lines: list[str] = []
    must = trace.get("must_pass") or {}
    if must.get("checks"):
        details = "、".join(
            f"{c.get('name')}（{c.get('actual')}）" for c in must["checks"] if c.get("passed")
        )
        lines.append(f"・必要條件 {must.get('passed')}/{must.get('total')} 通過：{details}")
    bonus = trace.get("bonus") or {}
    if bonus.get("checks"):
        details = "、".join(
            f"{c.get('name')}（{c.get('actual')}）" for c in bonus["checks"] if c.get("passed")
        )
        lines.append(
            f"・加分條件通過 {bonus.get('passed')} 項（門檻 {bonus.get('required')} 項）：{details}"
        )
    return lines


def _format_valuation(pick: dict[str, Any]) -> str | None:
    valuation = pick.get("valuation") or {}
    bands = [valuation.get(k) for k in ("fair_value_low", "fair_value_mid", "fair_value_high")]
    if not all(isinstance(b, int | float) for b in bands):
        return None
    method = valuation.get("method") or "估值模型"
    return (
        f"估值參考帶（{method}，未納入產業週期與成長率，不是目標價）："
        f"便宜 {bands[0]:,.1f}／合理 {bands[1]:,.1f}／昂貴 {bands[2]:,.1f}"
    )


def _format_value_trap(interpretation: dict[str, Any]) -> str | None:
    check = interpretation.get("value_trap_check")
    reason = interpretation.get("value_trap_reason") or ""
    if check == "no_concern":
        return "價值陷阱檢查：AI 未發現疑慮"
    if check in (None, "", "not_applicable"):
        return None
    return f"價值陷阱檢查：{check}" + (f"（{reason}）" if reason else "")


def _format_tracking(pick: dict[str, Any]) -> str | None:
    tracking = pick.get("tracking") or {}
    entry = tracking.get("entry_close_adj") or tracking.get("entry_price_snapshot")
    if not entry or tracking.get("return_current") is None:
        return None
    status = "追蹤完成" if tracking.get("complete") else "追蹤中"
    return (
        f"入選後表現：入選價 {entry:,.2f}（{tracking.get('entry_date', '')}），"
        f"截至 {tracking.get('as_of', '')} 報酬 {tracking['return_current']:+.1%}（{status}）"
    )


_INTERNAL_FIELD_RE = re.compile(r"\s*scoring_trace(?: 中的規則明細)?\s*")


def _readable(text: str) -> str:
    # AI 解讀失敗時的 fallback 文字寫著內部欄位名，別讓模型照抄給使用者
    return _INTERNAL_FIELD_RE.sub("規則檢核", text)


def _format_detail(report: dict[str, Any], profile: str, pick: dict[str, Any]) -> str:
    interpretation = pick.get("interpretation") or {}
    lines = [
        _report_heading(report, profile),
        (
            f"{_stock_label(pick)}{pick.get('industry', '')}"
            f"｜全名單第 {pick.get('rank_overall')} 名、產業內第 {pick.get('rank_in_industry')} 名"
            f"｜評等 {pick.get('final_grade', '')}"
        ),
    ]
    if interpretation.get("narrative"):
        lines.append(f"入選理由（AI 解讀）：{_readable(interpretation['narrative'])}")
    lines.extend(f"・{item}" for item in interpretation.get("key_context") or [])
    rules = _format_rules(pick)
    if rules:
        lines.append("規則檢核：")
        lines.extend(rules)
    lines.extend(
        line
        for line in (
            _format_valuation(pick),
            _format_value_trap(interpretation),
            _format_tracking(pick),
        )
        if line
    )
    warnings = interpretation.get("warnings") or []
    if warnings:
        lines.append("風險提示：")
        lines.extend(f"・{_readable(w)}" for w in warnings)
    lines.append("這是依固定規則篩選的結果，不是買進建議。")
    lines.append(_evidence_block(profile))
    return "\n".join(lines)


def _matches(pick: dict[str, Any], query: str) -> bool:
    code = _code(str(pick.get("ticker", ""))).upper()
    digits = re.search(r"\d{4,6}", query)
    if digits:
        return digits.group(0) == code
    name = str(pick.get("name", "")).upper()
    q = query.strip().upper()
    return len(q) >= 2 and (q == name or q in name)


@tool
def get_screener_picks(
    profile: Literal["momentum", "value"] | None = None,
    ticker: str | None = None,
    *,
    config: RunnableConfig,
) -> str:
    """查詢 Navi 智能選股報告：系統每週日盤後依固定規則篩選出的台股名單（動能策略、價值策略）。

    使用時機：使用者提到「選股 / 選股名單 / 入選 / 這週選了哪些 / 某檔為什麼被選進來」。
    使用者沒有提到選股或名單時不要用：個股的股價、技術面、基本面請用 get_stock_price、
    analyze_technicals、analyze_fundamentals（那些是即時數據；本工具是報告產出當下的評語）。

    回傳內容附有「策略證據」揭露，轉述名單或入選理由時必須一併告知使用者。

    Args:
        profile: "momentum"（動能策略）或 "value"（價值策略）；使用者沒指定就省略，兩種都查。
        ticker: 股票代號或名稱（如 "2421" 或 "建準"）。指定時回傳該檔的入選理由、規則檢核、
            估值參考帶與入選後表現；省略則回傳名單摘要。
    """
    try:
        denied = _access_denied_message(user_id_from(config))
        if denied:
            return f"⚠️ {denied}{_NO_LIST_HINT}"

        profiles = [profile] if profile else list(PROFILE_LABELS)
        sections: list[str] = []
        misses: list[str] = []
        for prof in profiles:
            report = find_latest_report(prof)
            if report is None:
                misses.append(f"目前還沒有{PROFILE_LABELS[prof]}的選股報告。")
                continue
            picks = load_pick_docs(str(report.get("report_id", "")))
            if not ticker:
                sections.append(_format_list(report, prof, picks))
                continue
            matched = [p for p in picks if _matches(p, ticker)]
            if matched:
                sections.extend(_format_detail(report, prof, p) for p in matched)
            else:
                label = _report_label(report)
                misses.append(f"{ticker} 不在最新一期{PROFILE_LABELS[prof]}名單中（{label}）。")
    except Exception:
        logger.exception("get_screener_picks failed")
        return f"⚠️ 選股報告暫時無法取得。{_NO_LIST_HINT}"

    return "\n\n".join(sections + misses)
