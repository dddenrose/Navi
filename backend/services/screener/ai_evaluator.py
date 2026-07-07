"""Stage 3 — LLM 解讀層（不再是評估者）.

對 Stage 2 的 qualified picks 做質性補充：
  - 把規則語言翻譯成投資邏輯（narrative）
  - 補充規則看不到的脈絡（key_context）
  - 標示風險（warnings）
  - Value profile 額外做 value-trap 偵測

LLM 不做：
  - 不決定 picks 篩選（Stage 2 已定）
  - 不寫目標價、停損（valuation.py 已算）
  - 不寫 confidence（final_grade 由規則決定）

v2 強化：
  - 動態 system prompt（依 profile 切換 horizon / value-trap playbook）
  - <allowed_numbers> 白名單 + narrative 後處理偵測幻覺
  - 失敗 retry（指數退避），最終仍失敗回傳 placeholder interpretation
"""

from __future__ import annotations

import asyncio
import logging
import xml.sax.saxutils as saxutils
from dataclasses import dataclass

import vertexai
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI

from config import settings
from services.screener.factor_scorer import EvaluatedStock
from services.screener.prompts import (
    StockInterpretation,
    build_interpreter_system_prompt,
    build_interpreter_user_prompt,
    format_allowed_numbers,
    validate_narrative,
)

logger = logging.getLogger(__name__)

# Retry / hallucination 控制
_MAX_RETRIES = 2  # 總嘗試次數 = _MAX_RETRIES + 1
_MAX_NARRATIVE_VIOLATIONS = 1  # 容許數字 token 違規上限（>= 此值即視為幻覺）
_RETRY_BASE_DELAY = 0.6


@dataclass
class InterpretedPick:
    evaluated: EvaluatedStock
    interpretation: StockInterpretation


def _build_llm(model_name: str | None = None) -> ChatVertexAI:
    vertexai.init(project=settings.google_cloud_project)
    return ChatVertexAI(
        model_name=model_name or settings.screener_llm_model,
        temperature=0.2,
        project=settings.google_cloud_project,
    )


def _x(s: str) -> str:
    return saxutils.escape(s)


def _fmt(v: float | None, *, pct: bool = False, digits: int = 2) -> str:
    if v is None:
        return "N/A"
    if pct:
        return f"{v * 100:.{digits}f}%"
    return f"{v:.{digits}f}"


def _checks_xml(tag: str, checks) -> str:
    if not checks:
        return f"<{tag}/>"
    lines = [f"<{tag}>"]
    for c in checks:
        lines.append(
            f"  <check id=\"{_x(c.rule_id)}\" passed=\"{str(c.passed).lower()}\">"
            f"<name>{_x(c.name)}</name>"
            f"<rule>{_x(c.rule)}</rule>"
            f"<actual>{_x(c.actual)}</actual>"
            f"<reference>{_x(c.reference)}</reference>"
            f"</check>"
        )
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def _build_snapshot_xml(es: EvaluatedStock, profile: str) -> str:
    d = es.data
    t = es.trace
    v = es.valuation

    val_block = ""
    if v is not None and v.fair_value_mid is not None:
        val_block = (
            "<valuation>\n"
            f"  <method>{_x(v.method)}</method>\n"
            f"  <fair_value_low>{v.fair_value_low}</fair_value_low>\n"
            f"  <fair_value_mid>{v.fair_value_mid}</fair_value_mid>\n"
            f"  <fair_value_high>{v.fair_value_high}</fair_value_high>\n"
            f"  <buy_zone_upper>{v.buy_zone_upper}</buy_zone_upper>\n"
            f"  <implied_upside_mid_pct>{v.implied_upside_mid_pct}</implied_upside_mid_pct>\n"
            "</valuation>"
        )

    # Derived signals — 給 LLM 判讀 value-trap 用（不新增 fetch，只組合既有欄位）
    payout_ratio = None
    if d.dividend_yield is not None and d.pe is not None and d.pe > 0:
        payout_ratio = d.dividend_yield * d.pe  # ≈ 配息率

    pe_vs_industry = None
    if d.pe is not None and d.industry_pe_median:
        pe_vs_industry = d.pe / d.industry_pe_median - 1  # 相對折溢價

    derived_block = (
        "<derived>\n"
        f"  <payout_ratio_est>{_fmt(payout_ratio, pct=True) if payout_ratio is not None else 'N/A'}</payout_ratio_est>\n"
        f"  <pe_vs_industry_median>{_fmt(pe_vs_industry, pct=True) if pe_vs_industry is not None else 'N/A'}</pe_vs_industry_median>\n"
        "</derived>"
    )

    return f"""\
<stock>
  <ticker>{_x(d.ticker)}</ticker>
  <name>{_x(d.name)}</name>
  <industry>{_x(d.industry)}</industry>
  <industry_size>{es.industry_size}</industry_size>
  <industry_rank>{es.industry_rank}</industry_rank>
  <final_grade>{_x(t.final_grade)}</final_grade>
  <profile>{_x(profile)}</profile>

  <snapshot>
    <price>{_fmt(d.price)}</price>
    <pe>{_fmt(d.pe)}</pe>
    <pb>{_fmt(d.pb)}</pb>
    <dividend_yield>{_fmt(d.dividend_yield, pct=True)}</dividend_yield>
    <roe_3y_avg>{_fmt(d.roe_3y_avg, pct=True)}</roe_3y_avg>
    <revenue_cagr_3y>{_fmt(d.revenue_cagr_3y, pct=True)}</revenue_cagr_3y>
    <revenue_yoy_latest>{_fmt(d.revenue_yoy_latest, pct=True)}</revenue_yoy_latest>
    <fcf_positive_years>{d.fcf_positive_years if d.fcf_positive_years is not None else 'N/A'}</fcf_positive_years>
    <eps_positive_quarters>{d.eps_positive_quarters if d.eps_positive_quarters is not None else 'N/A'}</eps_positive_quarters>
    <debt_ratio>{_fmt(d.debt_ratio, pct=True)}</debt_ratio>
    <gross_margin_std_4q>{_fmt(d.gross_margin_std_4q, pct=True)}</gross_margin_std_4q>
    <return_3m>{_fmt(d.return_3m, pct=True)}</return_3m>
    <return_6m>{_fmt(d.return_6m, pct=True)}</return_6m>
    <rel_strength_6m>{_fmt(d.rel_strength_6m, pct=True)}</rel_strength_6m>
    <rsi_14>{_fmt(d.rsi_14)}</rsi_14>
    <foreign_net_20d>{d.foreign_net_20d if d.foreign_net_20d is not None else 'N/A'}</foreign_net_20d>
    <industry_pe_median>{_fmt(d.industry_pe_median)}</industry_pe_median>
    <industry_pb_median>{_fmt(d.industry_pb_median)}</industry_pb_median>
  </snapshot>

  {derived_block}

  <scoring_trace>
    <verdict>{_x(t.verdict)}</verdict>
    <must_pass passed="{t.must_pass_count}" total="{t.must_pass_total}">
{_checks_xml('items', t.must_pass)}
    </must_pass>
    <bonus passed="{t.bonus_passed}" required="{t.bonus_required}">
{_checks_xml('items', t.bonus)}
    </bonus>
  </scoring_trace>

  {val_block}
</stock>
"""


def _build_allowed_numbers(es: EvaluatedStock) -> tuple[dict[str, str], dict[str, float]]:
    """產出兩份白名單：
      - text_map：給 prompt 顯示用（含單位字串）
      - num_map：給 `validate_narrative` 用（原始數值）
    """
    d = es.data
    v = es.valuation

    raw: dict[str, float | None] = {
        "price": d.price,
        "pe": d.pe,
        "pb": d.pb,
        "dividend_yield": d.dividend_yield,
        "roe_3y_avg": d.roe_3y_avg,
        "revenue_cagr_3y": d.revenue_cagr_3y,
        "revenue_yoy_latest": d.revenue_yoy_latest,
        "debt_ratio": d.debt_ratio,
        "current_ratio": d.current_ratio,
        "gross_margin_std_4q": d.gross_margin_std_4q,
        "return_3m": d.return_3m,
        "return_6m": d.return_6m,
        "rel_strength_6m": d.rel_strength_6m,
        "rsi_14": d.rsi_14,
        "industry_pe_median": d.industry_pe_median,
        "industry_pb_median": d.industry_pb_median,
    }
    # Derived
    if d.dividend_yield is not None and d.pe is not None and d.pe > 0:
        raw["payout_ratio_est"] = d.dividend_yield * d.pe
    if d.pe is not None and d.industry_pe_median:
        raw["pe_vs_industry_median"] = d.pe / d.industry_pe_median - 1

    if v is not None:
        for k in (
            "fair_value_low", "fair_value_mid", "fair_value_high",
            "buy_zone_upper", "implied_upside_mid_pct",
        ):
            raw[k] = getattr(v, k, None)

    pct_fields = {
        "dividend_yield", "roe_3y_avg", "revenue_cagr_3y", "revenue_yoy_latest",
        "debt_ratio", "gross_margin_std_4q",
        "return_3m", "return_6m", "rel_strength_6m",
        "payout_ratio_est", "pe_vs_industry_median", "implied_upside_mid_pct",
    }

    text_map: dict[str, str] = {}
    num_map: dict[str, float] = {}
    for k, val in raw.items():
        if val is None:
            continue
        num_map[k] = float(val)
        if k in pct_fields:
            # implied_upside_mid_pct 已是百分比量級，其餘是小數比率
            if k == "implied_upside_mid_pct":
                text_map[k] = f"{val:.2f}%"
            else:
                text_map[k] = f"{val * 100:.2f}%"
        elif k == "price" or k.startswith("fair_value") or k == "buy_zone_upper":
            text_map[k] = f"{val:.2f} 元"
        else:
            text_map[k] = f"{val:.2f}"
    return text_map, num_map


def _fallback_interpretation(es: EvaluatedStock) -> StockInterpretation:
    """LLM 終局失敗時的 placeholder，避免該檔在報告中消失。"""
    return StockInterpretation(
        narrative=(
            f"{es.data.name}（{es.data.ticker}）已通過量化規則的資格化篩選，"
            "但本期質性解讀產生失敗，請以 scoring_trace 中的規則明細為主要依據。"
        ),
        key_context=[],
        warnings=["本檔自動解讀失敗，建議人工複核 scoring_trace。"],
        value_trap_check="no_concern",
        value_trap_reason="",
    )


def _all_text_for_validation(result: StockInterpretation) -> str:
    parts = [result.narrative or ""]
    parts.extend(result.key_context or [])
    parts.extend(result.warnings or [])
    parts.append(result.value_trap_reason or "")
    return "\n".join(parts)


async def _interpret_one(
    structured_llm,
    es: EvaluatedStock,
    profile: str,
) -> InterpretedPick:
    """單檔解讀，含 retry + 數字幻覺驗證 + fallback。"""
    snapshot = _build_snapshot_xml(es, profile)
    allowed_text, allowed_num = _build_allowed_numbers(es)
    allowed_xml = format_allowed_numbers(allowed_text)
    system_prompt = build_interpreter_system_prompt(profile)

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=build_interpreter_user_prompt(profile, snapshot, allowed_xml),
            ),
        ]
        try:
            result = await structured_llm.ainvoke(messages)
        except Exception as e:
            last_error = e
            logger.warning(
                "LLM interpret error for %s (attempt %d/%d): %s",
                es.data.ticker, attempt + 1, _MAX_RETRIES + 1, e,
            )
            await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
            continue

        if not isinstance(result, StockInterpretation):
            logger.warning(
                "Unexpected LLM output type for %s: %s",
                es.data.ticker, type(result),
            )
            await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
            continue

        # Momentum profile：強制覆蓋 value_trap 欄位（與 prompt 對齊的雙重保險）
        if profile == "momentum":
            result.value_trap_check = "no_concern"
            result.value_trap_reason = ""

        # 數字幻覺檢查
        violations = validate_narrative(
            _all_text_for_validation(result), allowed_num,
        )
        if len(violations) > _MAX_NARRATIVE_VIOLATIONS and attempt < _MAX_RETRIES:
            logger.info(
                "Narrative hallucination detected for %s (attempt %d): %s — retrying",
                es.data.ticker, attempt + 1, violations[:5],
            )
            await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
            continue

        if violations:
            logger.warning(
                "Narrative hallucination remained for %s after retries: %s",
                es.data.ticker, violations[:5],
            )

        logger.info(
            "Interpreted %s: grade=%s value_trap=%s violations=%d",
            es.data.ticker, es.trace.final_grade,
            result.value_trap_check, len(violations),
        )
        return InterpretedPick(evaluated=es, interpretation=result)

    logger.error(
        "LLM interpret failed for %s after %d attempts (last_error=%s)",
        es.data.ticker, _MAX_RETRIES + 1, last_error,
    )
    return InterpretedPick(
        evaluated=es, interpretation=_fallback_interpretation(es),
    )


async def interpret_picks(
    picks: list[EvaluatedStock],
    *,
    profile: str = "value",
    max_concurrency: int = 4,
    model_name: str | None = None,
) -> list[InterpretedPick]:
    """並行對所有 qualified picks 跑 LLM 解讀。

    與 v1 差異：失敗的 pick **不再消失**，而是回傳帶 placeholder 的
    InterpretedPick（讓使用者知道有檔解讀失敗，需人工複核）。
    """
    if not picks:
        return []

    base_llm = _build_llm(model_name)
    structured_llm = base_llm.with_structured_output(StockInterpretation)

    sem = asyncio.Semaphore(max_concurrency)

    async def _bound(es: EvaluatedStock) -> InterpretedPick:
        async with sem:
            return await _interpret_one(structured_llm, es, profile)

    results = await asyncio.gather(*[_bound(es) for es in picks])
    fallbacks = sum(
        1 for r in results
        if r.interpretation.warnings
        and r.interpretation.warnings[0].startswith("本檔自動解讀失敗")
    )
    logger.info(
        "Stage 3 [%s]: %d picks → %d interpreted (%d fallback) (model=%s)",
        profile, len(picks), len(results), fallbacks,
        model_name or settings.screener_llm_model,
    )
    return results
