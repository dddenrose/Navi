"""Screener Orchestrator — 串接 Stage 1 → 2 → 3 並寫入 Firestore.

公開入口：`run_screener()` 與 `run_screener_async()`。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any

from google.cloud import firestore as firestore_module

from services.firestore_client import get_db
from services.screener.ai_evaluator import EvaluatedPick, evaluate_candidates
from services.screener.factor_scorer import (
    Profile,
    ScoredStock,
    score_universe,
    top_n_per_industry,
)
from services.screener.universe import load_universe

logger = logging.getLogger(__name__)

REPORTS_COLLECTION = "screener_reports"


def _make_report_id(profile: str, frequency: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{when:%Y%m%d}-{frequency}-{profile}"


def _scored_to_pick_doc(pick: EvaluatedPick) -> dict[str, Any]:
    sc = pick.scored
    f = sc.factors
    e = pick.evaluation
    return {
        "ticker": f.ticker,
        "name": f.name,
        "industry": f.industry,
        "rank_in_industry": sc.rank_in_industry,
        "factor_scores": {**sc.factor_scores, "final": sc.final_score},
        "snapshot": {
            "price": f.price,
            "pe": f.pe,
            "pb": f.pb,
            "roe": f.roe,
            "dividend_yield": f.dividend_yield,
            "revenue_growth": f.revenue_growth,
            "profit_margin": f.profit_margin,
            "return_3m": f.return_3m,
            "return_6m": f.return_6m,
            "rel_strength_3m": f.rel_strength,
            "volume_expansion": f.volume_expansion,
            "foreign_consecutive_days": f.foreign_consecutive_days,
            "foreign_net_5d": f.foreign_net_5d,
            "margin_change_5d": f.margin_change_5d,
            "short_change_5d": f.short_change_5d,
        },
        "thesis": e.thesis,
        "kb_citations": e.kb_citations,
        "target_price": e.target_price.model_dump(),
        "upside_pct": e.upside_pct,
        "stop_loss": e.stop_loss,
        "risk_reward_ratio": e.risk_reward_ratio,
        "risks": e.risks,
        "confidence": e.confidence,
    }


def _persist_report(
    report_id: str,
    *,
    profile: str,
    frequency: str,
    universe_size: int,
    stage1_passed: int,
    stage2_passed: int,
    picks: list[EvaluatedPick],
    duration_seconds: float,
    industries_covered: list[str],
) -> None:
    db = get_db()
    doc_ref = db.collection(REPORTS_COLLECTION).document(report_id)
    doc_ref.set(
        {
            "report_id": report_id,
            "generated_at": firestore_module.SERVER_TIMESTAMP,
            "profile": profile,
            "frequency": frequency,
            "universe_size": universe_size,
            "stage1_passed": stage1_passed,
            "stage2_passed": stage2_passed,
            "final_count": len(picks),
            "industries_covered": industries_covered,
            "duration_seconds": round(duration_seconds, 1),
            "status": "completed",
        }
    )
    picks_coll = doc_ref.collection("picks")
    for pick in picks:
        picks_coll.document(pick.scored.factors.ticker).set(_scored_to_pick_doc(pick))
    logger.info("Persisted report %s with %d picks", report_id, len(picks))


async def run_screener_async(
    *,
    profile: Profile = "momentum",
    frequency: str = "daily",
    tickers: list[str] | None = None,
    top_per_industry: int = 3,
    confidence_threshold: int = 70,
    model_name: str | None = None,
    persist: bool = True,
    skip_stage3: bool = False,
    enable_chips: bool = True,
    min_turnover: float | None = None,
    min_market_cap: float | None = None,
) -> dict[str, Any]:
    """End-to-end screener pipeline.

    Args:
        profile: "value" or "momentum".
        frequency: "daily" or "weekly"（影響 report_id）。
        tickers: 自訂股票池；None 則使用 industry_mapper 全部。
        top_per_industry: Stage 2 → Stage 3 各產業取前幾檔。
        confidence_threshold: Stage 3 信心過濾值。
        model_name: 覆寫 LLM model（驗證階段建議用 gemini-2.5-flash 省錢）。
        persist: 是否寫入 Firestore。
        skip_stage3: 只跑 Stage 1+2 (零 LLM 成本驗證)。
    """
    start = time.perf_counter()
    report_id = _make_report_id(profile, frequency)
    logger.info("=== Run screener: report_id=%s profile=%s ===", report_id, profile)

    # Stage 1
    universe_kwargs = {}
    if min_turnover is not None:
        universe_kwargs["min_turnover"] = min_turnover
    if min_market_cap is not None:
        universe_kwargs["min_market_cap"] = min_market_cap
    universe = load_universe(tickers=tickers, **universe_kwargs)
    stage1_passed = len(universe)

    # Stage 2
    scored = score_universe(universe, profile=profile, enable_chips=enable_chips)
    candidates = top_n_per_industry(scored, n=top_per_industry)
    stage2_passed = len(candidates)
    industries_covered = sorted({s.factors.industry for s in candidates})

    # Stage 3 (optional)
    picks: list[EvaluatedPick] = []
    if not skip_stage3 and candidates:
        picks = await evaluate_candidates(
            candidates,
            profile=profile,
            confidence_threshold=confidence_threshold,
            model_name=model_name,
        )

    duration = time.perf_counter() - start

    if persist and not skip_stage3:
        try:
            _persist_report(
                report_id,
                profile=profile,
                frequency=frequency,
                universe_size=len(tickers) if tickers else stage1_passed,
                stage1_passed=stage1_passed,
                stage2_passed=stage2_passed,
                picks=picks,
                duration_seconds=duration,
                industries_covered=industries_covered,
            )
        except Exception as e:
            logger.exception("Persist failed: %s", e)

    return {
        "report_id": report_id,
        "profile": profile,
        "frequency": frequency,
        "duration_seconds": round(duration, 1),
        "stage1_passed": stage1_passed,
        "stage2_passed": stage2_passed,
        "final_count": len(picks),
        "industries_covered": industries_covered,
        "scored": scored,  # ScoredStock list（debug 用）
        "candidates": candidates,
        "picks": picks,
    }


def run_screener(**kwargs) -> dict[str, Any]:
    """Sync wrapper（CLI / Cloud Run sync handler 用）。"""
    return asyncio.run(run_screener_async(**kwargs))
