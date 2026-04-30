"""Quota Service — 使用者額度管理（Tier-based、自然日重置）.

提供：
- 使用者主檔 upsert（首次登入即建立）
- Tier 額度設定讀取（quota_configs collection）
- 每日用量檢查與原子 increment
- 用量歷史查詢（給後台用）
- Audit log 寫入
- Tier 更新 + Firebase custom claims 同步

時區：所有「今日」以 Asia/Taipei 為準。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore as firestore_module
from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore_client import get_db

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

USERS_COLLECTION = "users"
QUOTA_CONFIGS_COLLECTION = "quota_configs"
USAGE_COUNTERS_COLLECTION = "usage_counters"
USAGE_LOGS_COLLECTION = "usage_logs"

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
USAGE_TTL_DAYS = 90

# 預設 tier 設定（若 Firestore 沒有對應 doc 則 fallback）
DEFAULT_TIER_CONFIGS: dict[str, dict[str, Any]] = {
    "free": {"daily_limit": 10, "per_minute_limit": 5, "description": "免費方案"},
    "pro": {"daily_limit": 100, "per_minute_limit": 10, "description": "進階方案"},
    "unlimited": {"daily_limit": -1, "per_minute_limit": 30, "description": "無限方案"},
    "admin": {"daily_limit": -1, "per_minute_limit": 60, "description": "管理員"},
}

VALID_TIERS = set(DEFAULT_TIER_CONFIGS.keys())
VALID_STATUSES = {"active", "suspended"}


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class QuotaCheckResult:
    allowed: bool
    tier: str
    daily_limit: int  # -1 = unlimited
    used_today: int
    remaining: int  # -1 = unlimited
    reset_at: datetime  # Asia/Taipei midnight tomorrow (tz-aware)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reset_at"] = self.reset_at.isoformat()
        return d


# ── Time helpers ─────────────────────────────────────────────────────────────


def _now_taipei() -> datetime:
    return datetime.now(tz=TAIPEI_TZ)


def _today_str(now: datetime | None = None) -> str:
    n = now or _now_taipei()
    return n.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d")


def _next_midnight_taipei(now: datetime | None = None) -> datetime:
    n = now or _now_taipei()
    n_local = n.astimezone(TAIPEI_TZ)
    tomorrow = (n_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow


def _counter_doc_id(uid: str, day: str | None = None) -> str:
    return f"{uid}_{day or _today_str()}"


# ── User upsert ──────────────────────────────────────────────────────────────


def get_or_create_user(
    uid: str,
    email: str = "",
    display_name: str = "",
    default_tier: str = "free",
) -> dict[str, Any]:
    """Read or create users/{uid}; refresh last_active_at.

    Returns the user dict.
    """
    if not uid:
        raise ValueError("uid is required")

    db = get_db()
    doc_ref = db.collection(USERS_COLLECTION).document(uid)
    snap = doc_ref.get()
    now = firestore_module.SERVER_TIMESTAMP

    if snap.exists:
        data = snap.to_dict() or {}
        # Lightweight refresh of last_active_at (best effort)
        try:
            doc_ref.update({"last_active_at": now})
        except Exception:  # pragma: no cover - non critical
            logger.debug("Failed to update last_active_at for %s", uid, exc_info=True)
        data.setdefault("uid", uid)
        return data

    new_user: dict[str, Any] = {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "tier": default_tier,
        "status": "active",
        "custom_daily_limit": None,
        "notes": "",
        "created_at": now,
        "updated_at": now,
        "last_active_at": now,
    }
    doc_ref.set(new_user)
    logger.info("Created new user: uid=%s email=%s tier=%s", uid, email, default_tier)
    # Return with non-sentinel timestamps for caller (use local now)
    new_user["created_at"] = _now_taipei()
    new_user["updated_at"] = _now_taipei()
    new_user["last_active_at"] = _now_taipei()
    return new_user


def get_user(uid: str) -> dict[str, Any] | None:
    db = get_db()
    snap = db.collection(USERS_COLLECTION).document(uid).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    data.setdefault("uid", uid)
    return data


# ── Quota config ─────────────────────────────────────────────────────────────


def get_quota_config(tier: str) -> dict[str, Any]:
    """Return quota config for a tier (with fallback to defaults)."""
    if tier not in VALID_TIERS:
        logger.warning("Unknown tier %s, falling back to free", tier)
        tier = "free"

    db = get_db()
    snap = db.collection(QUOTA_CONFIGS_COLLECTION).document(tier).get()
    if snap.exists:
        data = snap.to_dict() or {}
        # Merge defaults to fill missing keys
        merged = {**DEFAULT_TIER_CONFIGS[tier], **data}
        merged["tier"] = tier
        return merged
    # Fallback
    return {**DEFAULT_TIER_CONFIGS[tier], "tier": tier}


def list_quota_configs() -> list[dict[str, Any]]:
    out = []
    for tier in ["free", "pro", "unlimited", "admin"]:
        out.append(get_quota_config(tier))
    return out


def update_quota_config(tier: str, updates: dict[str, Any], actor_uid: str) -> dict[str, Any]:
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}")

    allowed_keys = {"daily_limit", "per_minute_limit", "description"}
    clean: dict[str, Any] = {k: v for k, v in updates.items() if k in allowed_keys}
    if not clean:
        raise ValueError("No valid fields to update")

    if "daily_limit" in clean:
        v = int(clean["daily_limit"])
        if v < -1:
            raise ValueError("daily_limit must be >= -1")
        clean["daily_limit"] = v
    if "per_minute_limit" in clean:
        v = int(clean["per_minute_limit"])
        if v < 1:
            raise ValueError("per_minute_limit must be >= 1")
        clean["per_minute_limit"] = v

    clean["tier"] = tier
    clean["updated_at"] = firestore_module.SERVER_TIMESTAMP
    clean["updated_by"] = actor_uid

    db = get_db()
    db.collection(QUOTA_CONFIGS_COLLECTION).document(tier).set(clean, merge=True)
    return get_quota_config(tier)


# ── Effective limit ──────────────────────────────────────────────────────────


def _effective_daily_limit(user: dict[str, Any], config: dict[str, Any]) -> int:
    """custom_daily_limit (per-user override) takes precedence."""
    custom = user.get("custom_daily_limit")
    if custom is not None:
        return int(custom)
    return int(config.get("daily_limit", 10))


# ── Check & consume (atomic) ─────────────────────────────────────────────────


def check_and_consume(uid: str, email: str = "", display_name: str = "") -> QuotaCheckResult:
    """Atomically check daily quota and increment counter.

    Returns ``QuotaCheckResult``. On Firestore failure, fail-open (allow=True)
    with reason="firestore_error" so the site stays up.
    """
    if not uid:
        raise ValueError("uid required")

    try:
        user = get_or_create_user(uid, email=email, display_name=display_name)
    except Exception:
        logger.exception("Failed to load user %s, fail-open", uid)
        return QuotaCheckResult(
            allowed=True,
            tier="free",
            daily_limit=-1,
            used_today=0,
            remaining=-1,
            reset_at=_next_midnight_taipei(),
            reason="firestore_error",
        )

    # Suspended users blocked unconditionally
    if user.get("status") == "suspended":
        return QuotaCheckResult(
            allowed=False,
            tier=str(user.get("tier", "free")),
            daily_limit=0,
            used_today=0,
            remaining=0,
            reset_at=_next_midnight_taipei(),
            reason="account_suspended",
        )

    tier = str(user.get("tier", "free"))
    config = get_quota_config(tier)
    daily_limit = _effective_daily_limit(user, config)
    today = _today_str()
    reset_at = _next_midnight_taipei()

    db = get_db()
    counter_ref = db.collection(USAGE_COUNTERS_COLLECTION).document(_counter_doc_id(uid, today))

    # Unlimited path: skip transaction, just touch last_request_at
    if daily_limit == -1:
        try:
            counter_ref.set(
                {
                    "uid": uid,
                    "date": today,
                    "chat_count": firestore_module.Increment(1),
                    "last_request_at": firestore_module.SERVER_TIMESTAMP,
                    "expires_at": datetime.now(tz=timezone.utc)
                    + timedelta(days=USAGE_TTL_DAYS),
                },
                merge=True,
            )
        except Exception:  # pragma: no cover
            logger.warning("Failed to update unlimited counter for %s", uid, exc_info=True)
        return QuotaCheckResult(
            allowed=True,
            tier=tier,
            daily_limit=-1,
            used_today=0,
            remaining=-1,
            reset_at=reset_at,
        )

    # Limited path: atomic transaction
    @firestore_module.transactional
    def _txn(transaction: firestore_module.Transaction) -> tuple[bool, int]:
        snap = counter_ref.get(transaction=transaction)
        used = (snap.to_dict() or {}).get("chat_count", 0) if snap.exists else 0
        if used >= daily_limit:
            return (False, used)
        transaction.set(
            counter_ref,
            {
                "uid": uid,
                "date": today,
                "chat_count": used + 1,
                "last_request_at": firestore_module.SERVER_TIMESTAMP,
                "expires_at": datetime.now(tz=timezone.utc) + timedelta(days=USAGE_TTL_DAYS),
            },
            merge=True,
        )
        return (True, used + 1)

    try:
        allowed, used_after = _txn(db.transaction())
    except Exception:
        logger.exception("Quota transaction failed for %s, fail-open", uid)
        return QuotaCheckResult(
            allowed=True,
            tier=tier,
            daily_limit=daily_limit,
            used_today=0,
            remaining=daily_limit,
            reset_at=reset_at,
            reason="firestore_error",
        )

    if not allowed:
        return QuotaCheckResult(
            allowed=False,
            tier=tier,
            daily_limit=daily_limit,
            used_today=used_after,
            remaining=0,
            reset_at=reset_at,
            reason="daily_quota_exceeded",
        )

    return QuotaCheckResult(
        allowed=True,
        tier=tier,
        daily_limit=daily_limit,
        used_today=used_after,
        remaining=max(0, daily_limit - used_after),
        reset_at=reset_at,
    )


# ── Usage history ────────────────────────────────────────────────────────────


def get_user_usage(uid: str, days: int = 30) -> list[dict[str, Any]]:
    """Return per-day usage for the past ``days`` days (Asia/Taipei)."""
    db = get_db()
    today = _now_taipei()
    out: list[dict[str, Any]] = []
    for offset in range(days):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        snap = db.collection(USAGE_COUNTERS_COLLECTION).document(_counter_doc_id(uid, day)).get()
        if snap.exists:
            data = snap.to_dict() or {}
            out.append({"date": day, "chat_count": int(data.get("chat_count", 0))})
        else:
            out.append({"date": day, "chat_count": 0})
    return out


# ── Tier update ──────────────────────────────────────────────────────────────


def update_user(
    uid: str,
    actor_uid: str,
    *,
    tier: str | None = None,
    status: str | None = None,
    custom_daily_limit: int | None | object = ...,  # ... = no change
    notes: str | None = None,
) -> dict[str, Any]:
    """Update user fields. Use sentinel ``...`` to skip ``custom_daily_limit``;
    pass ``None`` to clear it (use tier default).
    """
    if not uid:
        raise ValueError("uid required")
    if uid == actor_uid and tier is not None:
        raise ValueError("Cannot change your own tier (lockout protection)")

    updates: dict[str, Any] = {"updated_at": firestore_module.SERVER_TIMESTAMP}
    new_tier: str | None = None
    if tier is not None:
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier}")
        updates["tier"] = tier
        new_tier = tier
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        updates["status"] = status
    if custom_daily_limit is not ...:
        if custom_daily_limit is not None:
            v = int(custom_daily_limit)  # type: ignore[arg-type]
            if v < -1:
                raise ValueError("custom_daily_limit must be >= -1")
            updates["custom_daily_limit"] = v
        else:
            updates["custom_daily_limit"] = None
    if notes is not None:
        updates["notes"] = str(notes)[:500]

    db = get_db()
    doc_ref = db.collection(USERS_COLLECTION).document(uid)
    if not doc_ref.get().exists:
        raise ValueError(f"User {uid} not found")
    doc_ref.set(updates, merge=True)

    # Sync custom claims when tier changes
    if new_tier is not None:
        try:
            import firebase_admin.auth as firebase_auth
            from services.firestore_client import _init_firebase

            _init_firebase()
            firebase_auth.set_custom_user_claims(
                uid, {"admin": new_tier == "admin", "tier": new_tier}
            )
            logger.info("Updated custom claims for %s: tier=%s", uid, new_tier)
        except Exception:
            logger.exception("Failed to set custom claims for %s", uid)

    return get_user(uid) or {}


# ── Audit log ────────────────────────────────────────────────────────────────


def write_usage_log(
    uid: str,
    email: str,
    tier: str,
    endpoint: str,
    *,
    conversation_id: str | None = None,
    question: str | None = None,
    blocked: bool = False,
    block_reason: str | None = None,
) -> None:
    """Best-effort audit log. Never raises."""
    try:
        db = get_db()
        log_id = uuid.uuid4().hex
        doc = {
            "uid": uid,
            "email": email,
            "tier": tier,
            "endpoint": endpoint,
            "conversation_id": conversation_id,
            "question_preview": (question or "")[:100],
            "blocked": blocked,
            "block_reason": block_reason,
            "timestamp": firestore_module.SERVER_TIMESTAMP,
            "expires_at": datetime.now(tz=timezone.utc) + timedelta(days=USAGE_TTL_DAYS),
        }
        db.collection(USAGE_LOGS_COLLECTION).document(log_id).set(doc)
    except Exception:
        logger.warning("Failed to write usage log for %s", uid, exc_info=True)


# ── Admin queries ────────────────────────────────────────────────────────────


def list_users(
    tier: str | None = None,
    status: str | None = None,
    email_query: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = get_db()
    query: Any = db.collection(USERS_COLLECTION)
    if tier:
        query = query.where(filter=FieldFilter("tier", "==", tier))
    if status:
        query = query.where(filter=FieldFilter("status", "==", status))
    docs = query.limit(max(1, min(limit, 500))).get()
    out = []
    for d in docs:
        data = d.to_dict() or {}
        data.setdefault("uid", d.id)
        if email_query:
            if email_query.lower() not in str(data.get("email", "")).lower():
                continue
        out.append(_serialize_user(data))
    return out


def _serialize_user(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Firestore timestamps to ISO strings for JSON output."""
    out = dict(data)
    for key in ("created_at", "updated_at", "last_active_at"):
        v = out.get(key)
        if v is not None and hasattr(v, "isoformat"):
            out[key] = v.isoformat()
        elif v is not None:
            out[key] = str(v)
    return out


def list_usage_logs(
    uid: str | None = None,
    blocked: bool | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    db = get_db()
    query: Any = db.collection(USAGE_LOGS_COLLECTION)
    if uid:
        query = query.where(filter=FieldFilter("uid", "==", uid))
    if blocked is not None:
        query = query.where(filter=FieldFilter("blocked", "==", blocked))
    docs = (
        query.order_by("timestamp", direction=firestore_module.Query.DESCENDING)
        .limit(max(1, min(limit, 500)))
        .get()
    )
    out = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        ts = data.get("timestamp")
        if ts is not None and hasattr(ts, "isoformat"):
            data["timestamp"] = ts.isoformat()
        elif ts is not None:
            data["timestamp"] = str(ts)
        data.pop("expires_at", None)
        out.append(data)
    return out


def get_global_usage_summary(days: int = 30) -> dict[str, Any]:
    """Aggregate usage across all users for the past ``days`` days."""
    db = get_db()
    today = _now_taipei()
    cutoff_dates = {
        (today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)
    }

    # Note: scan usage_counters; could grow large. Caller is admin only.
    docs = (
        db.collection(USAGE_COUNTERS_COLLECTION)
        .where(filter=FieldFilter("date", ">=", min(cutoff_dates)))
        .limit(10000)
        .get()
    )

    daily: dict[str, int] = {d: 0 for d in cutoff_dates}
    user_totals: dict[str, int] = {}
    total = 0
    active_users: set[str] = set()

    for d in docs:
        data = d.to_dict() or {}
        date = str(data.get("date", ""))
        if date not in cutoff_dates:
            continue
        count = int(data.get("chat_count", 0))
        uid = str(data.get("uid", ""))
        daily[date] = daily.get(date, 0) + count
        if uid:
            user_totals[uid] = user_totals.get(uid, 0) + count
            active_users.add(uid)
        total += count

    top = sorted(user_totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "days": days,
        "total_messages": total,
        "active_users": len(active_users),
        "daily_breakdown": [{"date": k, "count": daily[k]} for k in sorted(daily.keys())],
        "top_users": [{"uid": uid, "count": cnt} for uid, cnt in top],
    }
