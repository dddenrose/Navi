"""Unit tests for quota_service (offline — Firestore mocked)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from services import quota_service


# ── Time helper tests ────────────────────────────────────────────────────────


def test_today_str_taipei():
    """today_str should reflect Asia/Taipei date."""
    s = quota_service._today_str()
    # Format YYYY-MM-DD
    assert len(s) == 10 and s[4] == "-" and s[7] == "-"


def test_next_midnight_taipei_is_tomorrow_zero():
    nm = quota_service._next_midnight_taipei()
    nm_local = nm.astimezone(ZoneInfo("Asia/Taipei"))
    assert nm_local.hour == 0 and nm_local.minute == 0 and nm_local.second == 0
    # Should be in the future
    assert nm > datetime.now(tz=ZoneInfo("Asia/Taipei"))
    # Less than 24h+1m away
    assert nm - datetime.now(tz=ZoneInfo("Asia/Taipei")) <= timedelta(days=1, minutes=1)


# ── Effective limit ──────────────────────────────────────────────────────────


def test_effective_limit_uses_custom_when_present():
    user = {"custom_daily_limit": 50}
    cfg = {"daily_limit": 10}
    assert quota_service._effective_daily_limit(user, cfg) == 50


def test_effective_limit_uses_tier_when_no_custom():
    user = {"custom_daily_limit": None}
    cfg = {"daily_limit": 10}
    assert quota_service._effective_daily_limit(user, cfg) == 10


def test_effective_limit_supports_unlimited_override():
    user = {"custom_daily_limit": -1}
    cfg = {"daily_limit": 10}
    assert quota_service._effective_daily_limit(user, cfg) == -1


# ── get_quota_config fallback ────────────────────────────────────────────────


def test_get_quota_config_unknown_tier_falls_back_to_free():
    with patch.object(quota_service, "get_db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = (
            mock_doc
        )
        cfg = quota_service.get_quota_config("nonexistent")
        assert cfg["tier"] == "free"
        assert cfg["daily_limit"] == 10


def test_get_quota_config_known_tier_returns_default_when_missing_in_db():
    with patch.object(quota_service, "get_db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = (
            mock_doc
        )
        cfg = quota_service.get_quota_config("pro")
        assert cfg["tier"] == "pro"
        assert cfg["daily_limit"] == 100


# ── update_user validation ───────────────────────────────────────────────────


def test_update_user_blocks_self_tier_change():
    with pytest.raises(ValueError, match="lockout"):
        quota_service.update_user(uid="u1", actor_uid="u1", tier="free")


def test_update_user_rejects_invalid_tier():
    with patch.object(quota_service, "get_db"):
        with pytest.raises(ValueError, match="Invalid tier"):
            quota_service.update_user(uid="u1", actor_uid="admin", tier="bogus")


def test_update_user_rejects_invalid_status():
    with patch.object(quota_service, "get_db"):
        with pytest.raises(ValueError, match="Invalid status"):
            quota_service.update_user(uid="u1", actor_uid="admin", status="banned")


def test_update_user_rejects_negative_custom_limit():
    with patch.object(quota_service, "get_db"):
        with pytest.raises(ValueError, match="custom_daily_limit"):
            quota_service.update_user(
                uid="u1", actor_uid="admin", custom_daily_limit=-5
            )


# ── update_quota_config validation ───────────────────────────────────────────


def test_update_quota_config_invalid_tier():
    with pytest.raises(ValueError):
        quota_service.update_quota_config("bogus", {"daily_limit": 5}, actor_uid="admin")


def test_update_quota_config_no_valid_fields():
    with pytest.raises(ValueError, match="No valid"):
        quota_service.update_quota_config("free", {"foo": "bar"}, actor_uid="admin")


def test_update_quota_config_negative_daily_limit():
    with pytest.raises(ValueError):
        quota_service.update_quota_config(
            "free", {"daily_limit": -2}, actor_uid="admin"
        )
