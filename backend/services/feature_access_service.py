"""Feature access service — tier-based feature permissions.

Stores per-feature access rules in Firestore and provides a single check for
backend routes and frontend capability discovery.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from google.cloud import firestore as firestore_module

from services import quota_service
from services.firestore_client import get_db

logger = logging.getLogger(__name__)

FEATURE_ACCESS_CONFIGS_COLLECTION = "feature_access_configs"

DEFAULT_FEATURE_ACCESS_CONFIGS: dict[str, dict[str, Any]] = {
    "chat": {
        "feature_key": "chat",
        "display_name": "AI 對話",
        "description": "Navi AI 投資助理聊天",
        "allowed_tiers": ["free", "pro", "unlimited", "admin"],
        "enabled": True,
    },
    # 成本/價值對齊：stock 是便宜的 deterministic 查詢，開放 free 當漏斗入口；
    # 真正貴的是 chat（LLM）與 backtest/screener（運算+LLM），由額度與 tier 控制。
    "stock": {
        "feature_key": "stock",
        "display_name": "股票分析",
        "description": "個股報價、技術面與基本面查詢",
        "allowed_tiers": ["free", "pro", "unlimited", "admin"],
        "enabled": True,
    },
    "portfolio": {
        "feature_key": "portfolio",
        "display_name": "投資組合",
        "description": "持股紀錄與損益追蹤",
        "allowed_tiers": ["free", "pro", "unlimited", "admin"],
        "enabled": True,
    },
    "backtest": {
        "feature_key": "backtest",
        "display_name": "策略回測",
        "description": "策略績效回測工具",
        "allowed_tiers": ["pro", "unlimited", "admin"],
        "enabled": True,
    },
    "screener": {
        "feature_key": "screener",
        "display_name": "智能選股",
        "description": "AI 三階段選股報告與通知訂閱",
        "allowed_tiers": ["pro", "unlimited", "admin"],
        "enabled": True,
    },
}

FEATURE_ORDER = ["chat", "stock", "portfolio", "backtest", "screener"]
VALID_FEATURE_KEYS = set(DEFAULT_FEATURE_ACCESS_CONFIGS.keys())


@dataclass
class FeatureAccessResult:
    allowed: bool
    feature_key: str
    display_name: str
    tier: str
    status: str
    enabled: bool
    allowed_tiers: list[str]
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_config(feature_key: str) -> dict[str, Any]:
    if feature_key not in VALID_FEATURE_KEYS:
        raise ValueError(f"Invalid feature_key: {feature_key}")
    return dict(DEFAULT_FEATURE_ACCESS_CONFIGS[feature_key])


def _normalize_tiers(tiers: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for tier in tiers:
        if tier not in quota_service.VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier}")
        if tier not in seen:
            normalized.append(tier)
            seen.add(tier)
    if not normalized:
        raise ValueError("allowed_tiers must not be empty")
    return normalized


def _serialize_config(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    value = out.get("updated_at")
    if value is not None and hasattr(value, "isoformat"):
        out["updated_at"] = value.isoformat()
    elif value is not None:
        out["updated_at"] = str(value)
    return out


def get_feature_config(feature_key: str) -> dict[str, Any]:
    """Return a feature access config with Firestore overriding defaults."""
    default = _default_config(feature_key)
    try:
        snap = (
            get_db()
            .collection(FEATURE_ACCESS_CONFIGS_COLLECTION)
            .document(feature_key)
            .get()
        )
    except Exception:
        logger.warning("Failed to load feature access config %s", feature_key, exc_info=True)
        return default

    if not snap.exists:
        return default

    data = snap.to_dict() or {}
    merged = {**default, **data, "feature_key": feature_key}
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["allowed_tiers"] = _normalize_tiers(list(merged.get("allowed_tiers") or []))
    return _serialize_config(merged)


def list_feature_configs() -> list[dict[str, Any]]:
    return [get_feature_config(feature_key) for feature_key in FEATURE_ORDER]


def update_feature_config(
    feature_key: str,
    updates: dict[str, Any],
    actor_uid: str,
) -> dict[str, Any]:
    if feature_key not in VALID_FEATURE_KEYS:
        raise ValueError(f"Invalid feature_key: {feature_key}")

    allowed_keys = {"enabled", "allowed_tiers", "description"}
    clean: dict[str, Any] = {k: v for k, v in updates.items() if k in allowed_keys}
    if not clean:
        raise ValueError("No valid fields to update")

    if "enabled" in clean:
        clean["enabled"] = bool(clean["enabled"])
    if "allowed_tiers" in clean:
        clean["allowed_tiers"] = _normalize_tiers(list(clean["allowed_tiers"] or []))
    if "description" in clean:
        clean["description"] = str(clean["description"])[:300]

    clean["feature_key"] = feature_key
    clean["updated_at"] = firestore_module.SERVER_TIMESTAMP
    clean["updated_by"] = actor_uid

    get_db().collection(FEATURE_ACCESS_CONFIGS_COLLECTION).document(feature_key).set(
        clean, merge=True
    )
    return get_feature_config(feature_key)


def check_feature_access(
    feature_key: str,
    uid: str,
    *,
    email: str = "",
    display_name: str = "",
) -> FeatureAccessResult:
    if not uid:
        raise ValueError("uid required")

    config = get_feature_config(feature_key)
    user = quota_service.get_or_create_user(
        uid, email=email, display_name=display_name
    )
    tier = str(user.get("tier", "free"))
    status = str(user.get("status", "active"))
    enabled = bool(config.get("enabled", True))
    allowed_tiers = list(config.get("allowed_tiers") or [])

    reason: str | None = None
    allowed = True
    if status == "suspended":
        allowed = False
        reason = "account_suspended"
    elif not enabled:
        allowed = False
        reason = "feature_disabled"
    elif tier not in allowed_tiers:
        allowed = False
        reason = "tier_not_allowed"

    return FeatureAccessResult(
        allowed=allowed,
        feature_key=feature_key,
        display_name=str(config.get("display_name", feature_key)),
        tier=tier,
        status=status,
        enabled=enabled,
        allowed_tiers=allowed_tiers,
        reason=reason,
    )


def list_feature_access_for_user(
    uid: str,
    *,
    email: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    user = quota_service.get_or_create_user(uid, email=email, display_name=display_name)
    tier = str(user.get("tier", "free"))
    status = str(user.get("status", "active"))
    features = []
    for config in list_feature_configs():
        enabled = bool(config.get("enabled", True))
        allowed_tiers = list(config.get("allowed_tiers") or [])
        allowed = status != "suspended" and enabled and tier in allowed_tiers
        reason = None
        if status == "suspended":
            reason = "account_suspended"
        elif not enabled:
            reason = "feature_disabled"
        elif tier not in allowed_tiers:
            reason = "tier_not_allowed"
        features.append({**config, "allowed": allowed, "reason": reason})
    return {"tier": tier, "status": status, "features": features}
