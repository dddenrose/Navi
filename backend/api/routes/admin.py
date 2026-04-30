"""Admin API — 使用者額度與 tier 管理.

所有 endpoint 需要 `admin == True` custom claim + Firestore tier=admin。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.dependencies import require_admin
from services import quota_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class UpdateUserPayload(BaseModel):
    tier: str | None = Field(default=None, description="free | pro | unlimited | admin")
    status: str | None = Field(default=None, description="active | suspended")
    custom_daily_limit: int | None = Field(
        default=None, description="個別 daily limit override（-1 = 無限）；省略表示不變"
    )
    clear_custom_limit: bool = Field(
        default=False, description="若 true 則清除 custom_daily_limit (回到 tier 預設)"
    )
    notes: str | None = None


class UpdateQuotaConfigPayload(BaseModel):
    daily_limit: int | None = None
    per_minute_limit: int | None = None
    description: str | None = None


# ── Identity ─────────────────────────────────────────────────────────────────


@router.get("/me")
async def admin_me(user: dict = Depends(require_admin)):
    return {"admin": True, "uid": user.get("uid"), "email": user.get("email", "")}


# ── Users ────────────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(
    q: str | None = Query(default=None, description="email 模糊搜尋"),
    tier: str | None = None,
    status: str | None = None,
    limit: int = 50,
    _: dict = Depends(require_admin),
):
    users = quota_service.list_users(
        tier=tier, status=status, email_query=q, limit=limit
    )
    return {"users": users}


@router.get("/users/{uid}")
async def get_user_detail(uid: str, _: dict = Depends(require_admin)):
    user = quota_service.get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    usage = quota_service.get_user_usage(uid, days=30)
    return {"user": quota_service._serialize_user(user), "usage": usage}


@router.patch("/users/{uid}")
async def update_user(
    uid: str,
    payload: UpdateUserPayload,
    actor: dict = Depends(require_admin),
):
    actor_uid = actor.get("uid", "")
    custom: object
    if payload.clear_custom_limit:
        custom = None
    elif payload.custom_daily_limit is not None:
        custom = payload.custom_daily_limit
    else:
        custom = ...  # sentinel: no change

    try:
        updated = quota_service.update_user(
            uid=uid,
            actor_uid=actor_uid,
            tier=payload.tier,
            status=payload.status,
            custom_daily_limit=custom,
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user": quota_service._serialize_user(updated)}


# ── Quota configs ────────────────────────────────────────────────────────────


@router.get("/quota-configs")
async def list_quota_configs(_: dict = Depends(require_admin)):
    return {"configs": quota_service.list_quota_configs()}


@router.put("/quota-configs/{tier}")
async def update_quota_config(
    tier: str,
    payload: UpdateQuotaConfigPayload,
    actor: dict = Depends(require_admin),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        cfg = quota_service.update_quota_config(
            tier=tier, updates=updates, actor_uid=actor.get("uid", "")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"config": cfg}


# ── Usage / logs ─────────────────────────────────────────────────────────────


@router.get("/usage/summary")
async def usage_summary(
    days: int = Query(default=30, ge=1, le=90),
    _: dict = Depends(require_admin),
):
    return quota_service.get_global_usage_summary(days=days)


@router.get("/logs")
async def list_logs(
    uid: str | None = None,
    blocked: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(require_admin),
):
    logs = quota_service.list_usage_logs(uid=uid, blocked=blocked, limit=limit)
    return {"logs": logs}
