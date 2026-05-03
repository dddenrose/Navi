"""Screener Orchestrator — 串接 Stage 1 → 2 (rule engine) → 3 (LLM 解讀)。

新架構（vs 舊版 z-score 加權）:
  Stage 1: load_universe（含處置股排除）
  Stage 2: evaluate_universe → ScoringTrace + Valuation
  Stage 3: interpret_picks → StockInterpretation（純解讀，不決定數字）

公開入口: run_screener() / run_screener_async()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from google.cloud import firestore as firestore_module

from services.firestore_client import get_db
from services.screener.ai_evaluator import InterpretedPick, interpret_picks
from services.screener.factor_scorer import (
    EvaluatedStock,
    evaluate_universe,
    top_n_per_industry,
)
from services.screener.rules import Profile, RuleCheck
from services.screener.universe import load_universe

logger = logging.getLogger(__name__)

REPORTS_COLLECTION = "screener_reports"


def _make_report_id(profile: str, frequency: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{when:%Y%m%d}-{frequency}-{profile}"


def _check_to_dict(c: RuleCheck) -> dict[str, Any]:
    return {
        "rule_id": c.rule_id,
        "name": c.name,
        "rule": c.rule,
        "actual": c.actual,
        "reference": c.reference,
        "passed": c.passed,
        "severity": c.severity,
    }


def _trace_to_dict(es: EvaluatedStock) -> dict[str, Any]:
    t = es.trace
    return {
        "verdict": t.verdict,
        "final_grade": t.final_grade,
        "rejection_reason": t.rejection_reason,
        "missing_data_count": t.missing_data_count,
        "missing_data_rule_ids": t.missing_data_rule_ids,
        "stage1_checks": [_check_to_dict(c) for c in es.stage1_checks],
        "must_pass": {
            "passed": t.must_pass_count,
            "total": t.must_pass_total,
            "checks": [_check_to_dict(c) for c in t.must_pass],
        },
        "bonus": {
            "passed": t.bonus_passed,
            "required": t.bonus_required,
            "checks": [_check_to_dict(c) for c in t.bonus],
        },
        "disqualifier": {
            "triggered": t.disqualifier_triggered,
            "checks": [_check_to_dict(c) for c in t.disqualifier],
        },
    }


def _valuation_to_dict(es: EvaluatedStock) -> dict[str, Any]:
    if es.valuation is None:
        return {}
    v = es.valuation
    return {
        "method": v.method,
        "fair_value_low": v.fair_value_low,
        "fair_value_mid": v.fair_value_mid,
        "fair_value_high": v.fair_value_high,
        "buy_zone_upper": v.buy_zone_upper,
        "implied_upside_mid_pct": v.implied_upside_mid_pct,
        "data_used": v.data_used,
        "notes": v.notes,
    }


def _snapshot_to_dict(es: EvaluatedStock) -> dict[str, Any]:
    d = es.data
    return {
        "price": d.price,
        "pe": d.pe,
        "pb": d.pb,
        "market_cap": d.market_cap,
        "dividend_yield": d.dividend_yield,
        "roe_3y_avg": d.roe_3y_avg,
        "revenue_cagr_3y": d.revenue_cagr_3y,
        "revenue_yoy_latest": d.revenue_yoy_latest,
        "fcf_positive_years": d.fcf_positive_years,
        "eps_positive_quarters": d.eps_positive_quarters,
        "debt_ratio": d.debt_ratio,
        "current_ratio": d.current_ratio,
        "gross_margin_std_4q": d.gross_margin_std_4q,
        "eps_ttm": d.eps_ttm,
        "return_3m": d.return_3m,
        "return_6m": d.return_6m,
        "rel_strength_6m": d.rel_strength_6m,
        "sma_60": d.sma_60,
        "sma_120": d.sma_120,
        "volume_ratio_5_20": d.volume_ratio_5_20,
        "rsi_14": d.rsi_14,
        "high_60d": d.high_60d,
        "foreign_net_5d": d.foreign_net_5d,
        "foreign_net_20d": d.foreign_net_20d,
        "foreign_consecutive_days": d.foreign_consecutive_days,
        "industry_pe_median": d.industry_pe_median,
        "industry_pb_median": d.industry_pb_median,
        "industry_size": d.industry_size,
    }


def _pick_to_doc(p: InterpretedPick) -> dict[str, Any]:
    es = p.evaluated
    interp = p.interpretation
    d = es.data
    return {
        "ticker": d.ticker,
        "name": d.name,
        "industry": d.industry,
        "rank_in_industry": es.industry_rank,
        "industry_size": es.industry_size,
        "final_grade": es.trace.final_grade,
        "verdict": es.trace.verdict,
        "snapshot": _snapshot_to_dict(es),
        "scoring_trace": _trace_to_dict(es),
        "valuation": _valuation_to_dict(es),
        "interpretation": {
            "narrative": interp.narrative,
            "key_context": interp.key_context,
            "warnings": interp.warnings,
            "value_trap_check": interp.value_trap_check,
            "value_trap_reason": interp.value_trap_reason,
        },
    }


def _qualified_to_doc(es: EvaluatedStock) -> dict[str, Any]:
    """For skip_stage3 mode: store qualified picks without LLM interpretation."""
    d = es.data
    return {
        "ticker": d.ticker,
        "name": d.name,
        "industry": d.industry,
        "rank_in_industry": es.industry_rank,
        "industry_size": es.industry_size,
        "final_grade": es.trace.final_grade,
        "verdict": es.trace.verdict,
        "snapshot": _snapshot_to_dict(es),
        "scoring_trace": _trace_to_dict(es),
        "valuation": _valuation_to_dict(es),
        "interpretation": {
            "narrative": "",
            "key_context": [],
            "warnings": [],
            "value_trap_check": "no_concern",
            "value_trap_reason": "",
        },
    }


def _persist_report(
    report_id: str,
    *,
    profile: str,
    frequency: str,
    universe_size: int,
    stage1_passed: int,
    stage2_qualified: int,
    pick_docs: list[dict[str, Any]],
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
            "stage2_passed": stage2_qualified,  # 保留欄名相容性
            "stage2_qualified": stage2_qualified,
            "final_count": len(pick_docs),
            "industries_covered": industries_covered,
            "duration_seconds": round(duration_seconds, 1),
            "status": "completed",
        }
    )
    picks_coll = doc_ref.collection("picks")
    for doc in pick_docs:
        picks_coll.document(doc["ticker"]).set(doc)
    logger.info("Persisted report %s with %d picks", report_id, len(pick_docs))


async def run_screener_async(
    *,
    profile: Profile = "value",
    frequency: str = "weekly",
    tickers: list[str] | None = None,
    top_per_industry: int = 3,
    model_name: str | None = None,
    persist: bool = True,
    skip_stage3: bool = False,
    enable_chips: bool = True,
    enable_fundamentals: bool = True,
    min_turnover: float | None = None,
    min_market_cap: float | None = None,
) -> dict[str, Any]:
    """End-to-end screener pipeline (rule-based)."""
    start = time.perf_counter()
    report_id = _make_report_id(profile, frequency)
    logger.info("=== Run screener: report_id=%s profile=%s ===", report_id, profile)

    # Stage 1
    universe_kwargs: dict[str, Any] = {}
    if min_turnover is not None:
        universe_kwargs["min_turnover"] = min_turnover
    if min_market_cap is not None:
        universe_kwargs["min_market_cap"] = min_market_cap
    universe = load_universe(tickers=tickers, **universe_kwargs)
    stage1_passed = len(universe)

    # Stage 2
    evaluated = evaluate_universe(
        universe,
        profile=profile,
        enable_chips=enable_chips,
        enable_fundamentals=enable_fundamentals,
    )
    qualified = [es for es in evaluated if es.trace.is_qualified()]
    candidates = top_n_per_industry(evaluated, n=top_per_industry)
    industries_covered = sorted({es.data.industry for es in candidates})

    # Stage 3 (optional)
    pick_docs: list[dict[str, Any]] = []
    if skip_stage3:
        pick_docs = [_qualified_to_doc(es) for es in candidates]
    elif candidates:
        interpreted = await interpret_picks(
            candidates, profile=profile, model_name=model_name,
        )
        pick_docs = [_pick_to_doc(p) for p in interpreted]

    duration = time.perf_counter() - start

    if persist:
        try:
            _persist_report(
                report_id,
                profile=profile,
                frequency=frequency,
                universe_size=len(tickers) if tickers else stage1_passed,
                stage1_passed=stage1_passed,
                stage2_qualified=len(qualified),
                pick_docs=pick_docs,
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
        "stage2_qualified": len(qualified),
        "final_count": len(pick_docs),
        "industries_covered": industries_covered,
        "evaluated": evaluated,
        "candidates": candidates,
        "pick_docs": pick_docs,
    }


def run_screener(**kwargs) -> dict[str, Any]:
    """Sync wrapper（CLI / Cloud Run sync handler 用）。"""
    return asyncio.run(run_screener_async(**kwargs))
