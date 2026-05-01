"""Screener API — 三階段選股報告觸發 / 查詢.

- POST /api/screener/run        Scheduler 觸發（shared-secret 保護）
- GET  /api/screener/reports             列表
- GET  /api/screener/reports/latest      最新（依 profile/frequency 過濾）
- GET  /api/screener/reports/{id}        詳情 + picks
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from api.dependencies import verify_firebase_token
from config import settings
from services.firestore_client import get_db
from services.screener.email_sender import (
    disable_subscriber,
    get_subscriber,
    send_report_email,
    upsert_subscriber,
    verify_unsubscribe_token,
)
from services.screener.orchestrator import REPORTS_COLLECTION, run_screener_async

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screener", tags=["screener"])


# ── Auth：Scheduler 用 shared-secret，使用者用 Firebase Auth ─────────────────


async def verify_runner_token(
    x_scheduler_token: str | None = Header(default=None, alias="X-Scheduler-Token"),
) -> None:
    """簡易 shared-secret 認證，供 Cloud Scheduler 觸發 /run、/notify 使用.

    生產環境可改用 OIDC ID token + audience 驗證；MVP 先用 token 比對。
    若未設定 SCREENER_RUNNER_TOKEN，視為未啟用此 endpoint（拒絕所有呼叫）。
    """
    expected = getattr(settings, "screener_runner_token", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Screener runner is not configured (SCREENER_RUNNER_TOKEN missing).",
        )
    if x_scheduler_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler token.",
        )


# ── Request / Response models ────────────────────────────────────────────────


class RunRequest(BaseModel):
    profile: str = Field("momentum", pattern="^(value|momentum)$")
    frequency: str = Field("daily", pattern="^(daily|weekly)$")
    top_per_industry: int = Field(3, ge=1, le=10)
    confidence_threshold: int = Field(70, ge=0, le=100)
    model_name: str | None = None
    skip_stage3: bool = False
    enable_chips: bool = True
    tickers: list[str] | None = None


class RunResponse(BaseModel):
    report_id: str
    profile: str
    frequency: str
    duration_seconds: float
    stage1_passed: int
    stage2_passed: int
    final_count: int
    industries_covered: list[str]
    status: str = "completed"


class ReportSummary(BaseModel):
    report_id: str
    profile: str
    frequency: str
    final_count: int
    industries_covered: list[str] = []
    duration_seconds: float | None = None
    status: str = ""
    generated_at: Any | None = None


class PickDoc(BaseModel):
    ticker: str
    name: str = ""
    industry: str = ""
    rank_in_industry: int = 0
    factor_scores: dict[str, float] = {}
    snapshot: dict[str, Any] = {}
    thesis: str = ""
    kb_citations: list[str] = []
    target_price: dict[str, float] = {}
    upside_pct: float = 0
    stop_loss: float = 0
    risk_reward_ratio: float = 0
    risks: list[str] = []
    confidence: int = 0


class ReportDetail(BaseModel):
    report: ReportSummary
    picks_by_industry: dict[str, list[PickDoc]]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _doc_to_summary(doc: dict) -> ReportSummary:
    return ReportSummary(
        report_id=doc.get("report_id", ""),
        profile=doc.get("profile", ""),
        frequency=doc.get("frequency", ""),
        final_count=doc.get("final_count", 0),
        industries_covered=doc.get("industries_covered", []),
        duration_seconds=doc.get("duration_seconds"),
        status=doc.get("status", ""),
        generated_at=doc.get("generated_at"),
    )


def _load_picks(report_id: str) -> dict[str, list[PickDoc]]:
    db = get_db()
    picks_coll = db.collection(REPORTS_COLLECTION).document(report_id).collection("picks")
    by_industry: dict[str, list[PickDoc]] = {}
    for snap in picks_coll.stream():
        data = snap.to_dict() or {}
        pick = PickDoc(**{k: v for k, v in data.items() if k in PickDoc.model_fields})
        by_industry.setdefault(pick.industry or "未分類", []).append(pick)
    # 排序
    for group in by_industry.values():
        group.sort(key=lambda p: p.rank_in_industry)
    return by_industry


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/run",
    response_model=RunResponse,
    dependencies=[Depends(verify_runner_token)],
)
async def run_screener_endpoint(payload: RunRequest) -> RunResponse:
    """觸發一次 screener 跑流程（Stage 1 → 2 → 3 → Firestore）."""
    logger.info("Screener run requested: %s", payload.model_dump())
    result = await run_screener_async(
        profile=payload.profile,  # type: ignore[arg-type]
        frequency=payload.frequency,
        top_per_industry=payload.top_per_industry,
        confidence_threshold=payload.confidence_threshold,
        model_name=payload.model_name,
        skip_stage3=payload.skip_stage3,
        enable_chips=payload.enable_chips,
        tickers=payload.tickers,
        persist=True,
    )
    return RunResponse(
        report_id=result["report_id"],
        profile=result["profile"],
        frequency=result["frequency"],
        duration_seconds=result["duration_seconds"],
        stage1_passed=result["stage1_passed"],
        stage2_passed=result["stage2_passed"],
        final_count=result["final_count"],
        industries_covered=result["industries_covered"],
    )


@router.get(
    "/reports",
    response_model=list[ReportSummary],
    dependencies=[Depends(verify_firebase_token)],
)
async def list_reports(
    profile: str | None = Query(None, pattern="^(value|momentum)$"),
    frequency: str | None = Query(None, pattern="^(daily|weekly)$"),
    limit: int = Query(20, ge=1, le=100),
) -> list[ReportSummary]:
    """列出最近的 reports.

    MVP 量小（預期 < 1000 份），全部拉回來 Python 端排序 / filter，
    避免 Firestore composite index 需求；量大再加 index。
    """
    db = get_db()
    docs = [snap.to_dict() or {} for snap in db.collection(REPORTS_COLLECTION).stream()]
    docs.sort(key=lambda d: d.get("report_id", ""), reverse=True)
    out: list[ReportSummary] = []
    for doc in docs:
        if profile and doc.get("profile") != profile:
            continue
        if frequency and doc.get("frequency") != frequency:
            continue
        out.append(_doc_to_summary(doc))
        if len(out) >= limit:
            break
    return out


@router.get(
    "/reports/latest",
    response_model=ReportDetail,
    dependencies=[Depends(verify_firebase_token)],
)
async def latest_report(
    profile: str = Query("momentum", pattern="^(value|momentum)$"),
    frequency: str = Query("daily", pattern="^(daily|weekly)$"),
) -> ReportDetail:
    db = get_db()
    docs = [snap.to_dict() or {} for snap in db.collection(REPORTS_COLLECTION).stream()]
    docs.sort(key=lambda d: d.get("report_id", ""), reverse=True)
    target_doc: dict | None = None
    for doc in docs:
        if doc.get("profile") == profile and doc.get("frequency") == frequency:
            target_doc = doc
            break
    if target_doc is None:
        raise HTTPException(status_code=404, detail="No report found")
    return ReportDetail(
        report=_doc_to_summary(target_doc),
        picks_by_industry=_load_picks(target_doc.get("report_id", "")),
    )


@router.get(
    "/reports/{report_id}",
    response_model=ReportDetail,
    dependencies=[Depends(verify_firebase_token)],
)
async def get_report(report_id: str) -> ReportDetail:
    db = get_db()
    snap = db.collection(REPORTS_COLLECTION).document(report_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Report not found")
    doc = snap.to_dict() or {}
    return ReportDetail(
        report=_doc_to_summary(doc),
        picks_by_industry=_load_picks(report_id),
    )


# ── Single-pick detail ──────────────────────────────────────────────────────


@router.get(
    "/reports/{report_id}/picks/{ticker}",
    response_model=PickDoc,
    dependencies=[Depends(verify_firebase_token)],
)
async def get_pick(report_id: str, ticker: str) -> PickDoc:
    db = get_db()
    ref = (
        db.collection(REPORTS_COLLECTION)
        .document(report_id)
        .collection("picks")
        .document(ticker)
    )
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Pick not found")
    data = snap.to_dict() or {}
    return PickDoc(**{k: v for k, v in data.items() if k in PickDoc.model_fields})


# ── Email subscription ──────────────────────────────────────────────────────


class SubscriptionPayload(BaseModel):
    enabled: bool | None = None
    email: EmailStr | None = None
    profiles: list[str] | None = None
    frequencies: list[str] | None = None


class SubscriptionResponse(BaseModel):
    user_id: str
    email: str = ""
    enabled: bool = False
    profiles: list[str] = []
    frequencies: list[str] = []


@router.get(
    "/subscriptions",
    response_model=SubscriptionResponse,
)
async def get_my_subscription(
    user: dict = Depends(verify_firebase_token),
) -> SubscriptionResponse:
    user_id = user["uid"]
    sub = get_subscriber(user_id) or {}
    return SubscriptionResponse(
        user_id=user_id,
        email=sub.get("email") or user.get("email", ""),
        enabled=bool(sub.get("enabled", False)),
        profiles=sub.get("profiles") or ["momentum", "value"],
        frequencies=sub.get("frequencies") or ["weekly"],
    )


@router.put(
    "/subscriptions",
    response_model=SubscriptionResponse,
)
async def update_my_subscription(
    payload: SubscriptionPayload,
    user: dict = Depends(verify_firebase_token),
) -> SubscriptionResponse:
    user_id = user["uid"]
    existing = get_subscriber(user_id) or {}
    update: dict = {}
    if payload.enabled is not None:
        update["enabled"] = payload.enabled
    # email 預設使用 Firebase token 所含 email
    update["email"] = (
        payload.email
        or existing.get("email")
        or user.get("email", "")
    )
    update["profiles"] = payload.profiles or existing.get("profiles") or [
        "momentum",
        "value",
    ]
    update["frequencies"] = payload.frequencies or existing.get(
        "frequencies"
    ) or ["weekly"]
    saved = upsert_subscriber(user_id, update)
    return SubscriptionResponse(
        user_id=user_id,
        email=saved.get("email", ""),
        enabled=bool(saved.get("enabled", False)),
        profiles=saved.get("profiles") or [],
        frequencies=saved.get("frequencies") or [],
    )


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str) -> HTMLResponse:
    """One-click unsubscribe via HMAC-signed token."""
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        return HTMLResponse(
            "<h1>連結無效或已過期</h1>",
            status_code=400,
        )
    ok = disable_subscriber(user_id)
    if not ok:
        return HTMLResponse("<h1>查無訂閱記錄</h1>", status_code=404)
    return HTMLResponse(
        "<h1>已取消訂閱</h1><p>你將不再收到 Navi 智能選股週報。</p>",
        status_code=200,
    )


# ── Email notify trigger (scheduler) ────────────────────────────────────────


class NotifyRequest(BaseModel):
    profile: str = Field("momentum", pattern="^(value|momentum)$")
    frequency: str = Field("weekly", pattern="^(daily|weekly)$")
    report_id: str | None = None  # None → 使用最新 report


class NotifyResponse(BaseModel):
    report_id: str
    sent: int
    skipped: int
    failed: int
    dry_run: bool


@router.post(
    "/notify",
    response_model=NotifyResponse,
    dependencies=[Depends(verify_runner_token)],
)
async def notify_subscribers(payload: NotifyRequest) -> NotifyResponse:
    """Render the latest matching report and email it to active subscribers."""
    db = get_db()
    target_id = payload.report_id
    if not target_id:
        docs = [snap.to_dict() or {} for snap in db.collection(REPORTS_COLLECTION).stream()]
        docs.sort(key=lambda d: d.get("report_id", ""), reverse=True)
        for doc in docs:
            if (
                doc.get("profile") == payload.profile
                and doc.get("frequency") == payload.frequency
            ):
                target_id = doc.get("report_id")
                break
        if not target_id:
            raise HTTPException(status_code=404, detail="No matching report to notify.")

    result = send_report_email(
        target_id, profile=payload.profile, frequency=payload.frequency
    )
    return NotifyResponse(
        report_id=target_id,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
        dry_run=result.dry_run,
    )
