"""Stage 3 — AI Evaluator.

對 Stage 2 篩出的候選股做 LLM 深度評估，產出結構化 ScreenerEvaluation。
為了控制成本與穩定性，MVP 不用 tool-calling agent，而是：
  1. 對每個 profile 預先做一次 search_knowledge 取得理論支撐文本（共用）
  2. 將 ScoredStock 的 snapshot 序列化成 XML
  3. 用 ChatVertexAI.with_structured_output() 強制 schema
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
from services.embedding_service import search_similar
from services.screener.factor_scorer import ScoredStock
from services.screener.prompts import (
    EVALUATOR_SYSTEM_PROMPT,
    ScreenerEvaluation,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


# Profile 對應的知識庫 query（一份 profile 共用，避免重複 embedding 成本）
_PROFILE_KB_QUERY = {
    "value": "價值投資 估值 PE PB 殖利率 護城河 風險管理 目標價",
    "momentum": "動量策略 均線 RSI 鈍化 三大法人解讀 量價關係 停損",
}


@dataclass
class EvaluatedPick:
    scored: ScoredStock
    evaluation: ScreenerEvaluation


def _build_llm(model_name: str | None = None) -> ChatVertexAI:
    vertexai.init(project=settings.google_cloud_project)
    return ChatVertexAI(
        model_name=model_name or settings.gemini_model_name,
        temperature=0.3,
        project=settings.google_cloud_project,
    )


def _kb_context(profile: str, top_k: int = 5) -> tuple[str, list[str]]:
    """預取 KB 相關段落，回傳 (拼接文字, 引用清單)."""
    query = _PROFILE_KB_QUERY.get(profile, profile)
    docs = search_similar(query, top_k=top_k)
    if not docs:
        return ("（知識庫無相關內容）", [])

    lines = []
    citations = []
    for i, d in enumerate(docs, 1):
        meta = d.get("metadata", {})
        title = meta.get("title", "")
        source = meta.get("source_file") or meta.get("category", "")
        content = d.get("content", "")
        if len(content) > 500:
            content = content[:500] + "…"
        lines.append(f"[{i}] {title}（{source}）\n{content}")
        if source:
            citations.append(source)
    return ("\n\n".join(lines), citations)


def _format_optional(v, fmt: str = "{:.2f}") -> str:
    if v is None:
        return "N/A"
    try:
        return fmt.format(v)
    except Exception:
        return str(v)


def _build_snapshot_xml(sc: ScoredStock, kb_text: str) -> str:
    f = sc.factors

    def x(s: str) -> str:
        return saxutils.escape(s)

    factor_lines = "\n".join(
        f"  <{k}>{v}</{k}>" for k, v in sc.factor_scores.items()
    )

    return f"""\
<stock>
  <ticker>{x(f.ticker)}</ticker>
  <name>{x(f.name)}</name>
  <industry>{x(f.industry)}</industry>
  <rank_in_industry>{sc.rank_in_industry}</rank_in_industry>
  <final_score>{sc.final_score}</final_score>
  <snapshot>
    <price>{_format_optional(f.price)}</price>
    <pe>{_format_optional(f.pe)}</pe>
    <pb>{_format_optional(f.pb)}</pb>
    <roe>{_format_optional(f.roe, "{:.2%}") if f.roe is not None else "N/A"}</roe>
    <dividend_yield>{_format_optional(f.dividend_yield, "{:.2%}") if f.dividend_yield is not None else "N/A"}</dividend_yield>
    <revenue_growth>{_format_optional(f.revenue_growth, "{:.2%}") if f.revenue_growth is not None else "N/A"}</revenue_growth>
    <profit_margin>{_format_optional(f.profit_margin, "{:.2%}") if f.profit_margin is not None else "N/A"}</profit_margin>
    <return_3m>{_format_optional(f.return_3m, "{:.2%}") if f.return_3m is not None else "N/A"}</return_3m>
    <return_6m>{_format_optional(f.return_6m, "{:.2%}") if f.return_6m is not None else "N/A"}</return_6m>
    <relative_strength_3m>{_format_optional(f.rel_strength, "{:.2%}") if f.rel_strength is not None else "N/A"}</relative_strength_3m>
    <volume_expansion>{_format_optional(f.volume_expansion)}</volume_expansion>
  </snapshot>
  <factor_scores>
{factor_lines}
  </factor_scores>
  <knowledge_base_excerpts>
{x(kb_text)}
  </knowledge_base_excerpts>
</stock>
"""


async def _evaluate_one(
    llm,
    sc: ScoredStock,
    profile: str,
    kb_text: str,
    default_citations: list[str],
) -> EvaluatedPick | None:
    snapshot = _build_snapshot_xml(sc, kb_text)
    messages = [
        SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
        HumanMessage(content=build_user_prompt(profile, snapshot)),
    ]
    try:
        result = await llm.ainvoke(messages)
    except Exception as e:
        logger.warning("LLM eval failed for %s: %s", sc.factors.ticker, e)
        return None

    if not isinstance(result, ScreenerEvaluation):
        # with_structured_output 失敗時 fallback
        logger.warning("Unexpected LLM output type for %s: %s", sc.factors.ticker, type(result))
        return None

    # 若 LLM 沒填 kb_citations，至少給 default
    if not result.kb_citations:
        result.kb_citations = default_citations[:3]

    logger.info(
        "Evaluated %s: confidence=%d upside=%.1f%%",
        sc.factors.ticker,
        result.confidence,
        result.upside_pct,
    )
    return EvaluatedPick(scored=sc, evaluation=result)


async def evaluate_candidates(
    candidates: list[ScoredStock],
    *,
    profile: str = "momentum",
    confidence_threshold: int = 70,
    max_concurrency: int = 4,
    model_name: str | None = None,
) -> list[EvaluatedPick]:
    """並行對候選股做 LLM 評估，回傳信心 ≥ threshold 的清單。"""
    if not candidates:
        return []

    kb_text, citations = _kb_context(profile)
    base_llm = _build_llm(model_name)
    structured_llm = base_llm.with_structured_output(ScreenerEvaluation)

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bound(sc: ScoredStock):
        async with semaphore:
            return await _evaluate_one(structured_llm, sc, profile, kb_text, citations)

    results = await asyncio.gather(*[_bound(sc) for sc in candidates])
    picks = [r for r in results if r is not None and r.evaluation.confidence >= confidence_threshold]
    logger.info(
        "Stage 3: %d candidates → %d picks (threshold=%d, model=%s)",
        len(candidates),
        len(picks),
        confidence_threshold,
        model_name or settings.gemini_model_name,
    )
    return picks
