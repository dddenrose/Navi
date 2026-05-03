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
    INTERPRETER_SYSTEM_PROMPT,
    StockInterpretation,
    build_interpreter_user_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class InterpretedPick:
    evaluated: EvaluatedStock
    interpretation: StockInterpretation


def _build_llm(model_name: str | None = None) -> ChatVertexAI:
    vertexai.init(project=settings.google_cloud_project)
    return ChatVertexAI(
        model_name=model_name or settings.gemini_model_name,
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
    <return_3m>{_fmt(d.return_3m, pct=True)}</return_3m>
    <return_6m>{_fmt(d.return_6m, pct=True)}</return_6m>
    <rel_strength_6m>{_fmt(d.rel_strength_6m, pct=True)}</rel_strength_6m>
    <rsi_14>{_fmt(d.rsi_14)}</rsi_14>
    <foreign_net_20d>{d.foreign_net_20d if d.foreign_net_20d is not None else 'N/A'}</foreign_net_20d>
  </snapshot>

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


async def _interpret_one(
    structured_llm,
    es: EvaluatedStock,
    profile: str,
) -> InterpretedPick | None:
    snapshot = _build_snapshot_xml(es, profile)
    messages = [
        SystemMessage(content=INTERPRETER_SYSTEM_PROMPT),
        HumanMessage(content=build_interpreter_user_prompt(profile, snapshot)),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
    except Exception as e:
        logger.warning("LLM interpret failed for %s: %s", es.data.ticker, e)
        return None

    if not isinstance(result, StockInterpretation):
        logger.warning(
            "Unexpected LLM output type for %s: %s",
            es.data.ticker, type(result),
        )
        return None

    # Momentum profile force-reset value_trap_check
    if profile == "momentum":
        result.value_trap_check = "no_concern"
        result.value_trap_reason = ""

    logger.info(
        "Interpreted %s: grade=%s value_trap=%s",
        es.data.ticker, es.trace.final_grade, result.value_trap_check,
    )
    return InterpretedPick(evaluated=es, interpretation=result)


async def interpret_picks(
    picks: list[EvaluatedStock],
    *,
    profile: str = "value",
    max_concurrency: int = 4,
    model_name: str | None = None,
) -> list[InterpretedPick]:
    """並行對所有 qualified picks 跑 LLM 解讀。失敗會被略過。"""
    if not picks:
        return []

    base_llm = _build_llm(model_name)
    structured_llm = base_llm.with_structured_output(StockInterpretation)

    sem = asyncio.Semaphore(max_concurrency)

    async def _bound(es: EvaluatedStock):
        async with sem:
            return await _interpret_one(structured_llm, es, profile)

    results = await asyncio.gather(*[_bound(es) for es in picks])
    out = [r for r in results if r is not None]
    logger.info(
        "Stage 3 [%s]: %d picks → %d interpreted (model=%s)",
        profile, len(picks), len(out),
        model_name or settings.gemini_model_name,
    )
    return out
