"""Unit tests for feature_access_service (offline — Firestore mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from services import feature_access_service


def test_default_screener_access_requires_paid_tier():
    with patch.object(feature_access_service, "get_db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = (
            mock_doc
        )
        cfg = feature_access_service.get_feature_config("screener")
    assert cfg["allowed_tiers"] == ["pro", "unlimited", "admin"]


def test_default_free_tier_features():
    """成本/價值對齊：便宜的 stock 查詢開放 free 當漏斗；貴的 screener 收費."""
    free_features = {
        key
        for key, cfg in feature_access_service.DEFAULT_FEATURE_ACCESS_CONFIGS.items()
        if "free" in cfg["allowed_tiers"]
    }
    assert free_features == {"chat", "portfolio", "stock"}


def test_paid_only_features_in_defaults():
    """付費功能僅剩 screener；回測已收斂到 Chat 的 agent tool，不再是獨立 feature."""
    paid_only = {
        key
        for key, cfg in feature_access_service.DEFAULT_FEATURE_ACCESS_CONFIGS.items()
        if "free" not in cfg["allowed_tiers"]
    }
    assert paid_only == {"screener"}
    assert feature_access_service.DEFAULT_FEATURE_ACCESS_CONFIGS["screener"][
        "allowed_tiers"
    ] == ["pro", "unlimited", "admin"]


def test_check_feature_access_allows_pro_user():
    with (
        patch.object(
            feature_access_service.quota_service,
            "get_or_create_user",
            return_value={"tier": "pro", "status": "active"},
        ),
        patch.object(
            feature_access_service,
            "get_feature_config",
            return_value={
                "feature_key": "screener",
                "display_name": "智能選股",
                "enabled": True,
                "allowed_tiers": ["pro", "admin"],
            },
        ),
    ):
        result = feature_access_service.check_feature_access("screener", "u1")
    assert result.allowed is True
    assert result.reason is None


def test_check_feature_access_blocks_free_user():
    with (
        patch.object(
            feature_access_service.quota_service,
            "get_or_create_user",
            return_value={"tier": "free", "status": "active"},
        ),
        patch.object(
            feature_access_service,
            "get_feature_config",
            return_value={
                "feature_key": "screener",
                "display_name": "智能選股",
                "enabled": True,
                "allowed_tiers": ["pro", "admin"],
            },
        ),
    ):
        result = feature_access_service.check_feature_access("screener", "u1")
    assert result.allowed is False
    assert result.reason == "tier_not_allowed"


def test_update_feature_config_rejects_invalid_tier():
    with pytest.raises(ValueError, match="Invalid tier"):
        feature_access_service.update_feature_config(
            "screener",
            {"allowed_tiers": ["free", "vip"]},
            actor_uid="admin",
        )


def test_update_feature_config_no_valid_fields():
    with pytest.raises(ValueError, match="No valid"):
        feature_access_service.update_feature_config(
            "screener",
            {"display_name": "Nope"},
            actor_uid="admin",
        )
