"""get_screener_picks：名單 / 單檔格式、權限、證據揭露."""

from unittest.mock import MagicMock, patch

import pytest

from services.feature_access_service import FeatureAccessResult
from services.screener.evidence import get_evidence
from tools.runtime import user_config
from tools.screener_tool import get_screener_picks

REPORTS = {
    "momentum": {
        "report_id": "20261011-weekly-momentum",
        "profile": "momentum",
        "frequency": "weekly",
    },
    "value": {"report_id": "20261011-weekly-value", "profile": "value", "frequency": "weekly"},
}


def _pick(ticker, name, rank, *, key_context=None, narrative="入選理由", warnings=None):
    return {
        "ticker": ticker,
        "name": name,
        "industry": "電子零組件",
        "rank_overall": rank,
        "rank_in_industry": 1,
        "final_grade": "Strong Pick",
        "scoring_trace": {
            "must_pass": {
                "passed": 2,
                "total": 2,
                "checks": [
                    {"name": "估值不貴", "passed": True, "actual": "PE 17.54"},
                    {"name": "獲利能力", "passed": True, "actual": "20.56%"},
                ],
            },
            "bonus": {
                "passed": 1,
                "required": 2,
                "checks": [
                    {"name": "成長性", "passed": True, "actual": "9.92%"},
                    {"name": "毛利穩定", "passed": False, "actual": "3.1%"},
                ],
            },
        },
        "valuation": {
            "method": "EPS × 產業 PE 區間",
            "fair_value_low": 215.63,
            "fair_value_mid": 323.61,
            "fair_value_high": 445.87,
        },
        "interpretation": {
            "narrative": narrative,
            "key_context": key_context if key_context is not None else ["本益比低於產業中位數"],
            "warnings": warnings or [],
            "value_trap_check": "no_concern",
        },
        "tracking": {
            "entry_close_adj": 168.0,
            "entry_date": "2026-10-11",
            "as_of": "2026-10-13",
            "return_current": 0.025,
            "complete": False,
        },
    }


PICKS = {
    "20261011-weekly-momentum": [_pick("6196.TW", "帆宣", 1)],
    "20261011-weekly-value": [_pick("2421.TW", "建準", 1), _pick("1590.TW", "亞德客-KY", 2)],
}


@pytest.fixture
def reports():
    with (
        patch("tools.screener_tool.find_latest_report", side_effect=REPORTS.get) as latest,
        patch("tools.screener_tool.load_pick_docs", side_effect=PICKS.get),
        patch("tools.screener_tool.settings", MagicMock(auth_required=False)),
    ):
        yield latest


def _run(**args):
    return get_screener_picks.invoke(args, config=user_config("u1"))


def test_model_cannot_see_or_set_the_user():
    # uid 走 config 注入；schema 裡只有 profile 和 ticker
    schema = get_screener_picks.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {"profile", "ticker"}
    assert schema["properties"]["profile"]["anyOf"][0]["enum"] == ["momentum", "value"]


def test_list_covers_both_profiles_with_dates_and_evidence(reports):
    out = _run()

    assert "動能策略（2026-10-11 週報），共 1 檔" in out
    assert "價值策略（2026-10-11 週報），共 2 檔" in out
    assert "1. 帆宣（6196）電子零組件｜Strong Pick｜本益比低於產業中位數" in out
    assert get_evidence("momentum")["headline"] in out
    assert get_evidence("value")["headline"] in out
    assert "不是買進建議" in out


def test_profile_limits_the_query(reports):
    out = _run(profile="value")

    assert "建準" in out
    assert "帆宣" not in out
    assert get_evidence("momentum")["headline"] not in out


def test_list_falls_back_to_rule_names_when_ai_interpretation_failed(reports):
    PICKS["20261011-weekly-value"].append(_pick("2385.TW", "群光", 3, key_context=[]))
    try:
        out = _run(profile="value")
    finally:
        PICKS["20261011-weekly-value"].pop()

    assert "3. 群光（2385）電子零組件｜Strong Pick｜通過規則：估值不貴、獲利能力" in out


@pytest.mark.parametrize("ticker", ["2421", "2421.TW", "建準", "建準 2421"])
def test_detail_matches_code_or_name(reports, ticker):
    out = _run(profile="value", ticker=ticker)

    assert "建準（2421）電子零組件｜全名單第 1 名、產業內第 1 名｜評等 Strong Pick" in out
    assert "必要條件 2/2 通過：估值不貴（PE 17.54）、獲利能力（20.56%）" in out
    # 未通過的加分條件不列為入選理由
    assert "加分條件通過 1 項（門檻 2 項）：成長性（9.92%）" in out
    assert "毛利穩定" not in out
    assert "便宜 215.6／合理 323.6／昂貴 445.9" in out
    assert "不是目標價" in out
    assert "報酬 +2.5%（追蹤中）" in out
    assert get_evidence("value")["headline"] in out


def test_detail_matches_partial_name(reports):
    assert "亞德客-KY（1590）" in _run(ticker="亞德客")


def test_detail_reports_profiles_where_the_stock_is_missing(reports):
    out = _run(ticker="建準")

    assert "建準（2421）" in out
    assert "建準 不在最新一期動能策略名單中（2026-10-11 週報）。" in out


def test_unknown_stock_gets_no_evidence_block(reports):
    out = _run(ticker="台積電")

    assert "台積電 不在最新一期動能策略名單中" in out
    assert "台積電 不在最新一期價值策略名單中" in out
    assert "策略證據" not in out


def test_internal_field_names_are_not_passed_to_the_model(reports):
    PICKS["20261011-weekly-value"].append(
        _pick(
            "2385.TW",
            "群光",
            3,
            narrative="本期質性解讀產生失敗，請以 scoring_trace 中的規則明細為主要依據。",
            warnings=["本檔自動解讀失敗，建議人工複核 scoring_trace。"],
        )
    )
    try:
        out = _run(ticker="2385")
    finally:
        PICKS["20261011-weekly-value"].pop()

    assert "scoring_trace" not in out
    assert "請以規則檢核為主要依據" in out


def test_missing_report(reports):
    reports.side_effect = lambda profile: None

    assert _run(profile="momentum") == "目前還沒有動能策略的選股報告。"


def test_firestore_error_tells_model_not_to_invent_a_list(reports):
    reports.side_effect = RuntimeError("firestore down")

    out = _run()

    assert out.startswith("⚠️ 選股報告暫時無法取得")
    assert "不要自行列出任何選股名單" in out


def _access(allowed, reason=None, tier="free"):
    return FeatureAccessResult(
        allowed=allowed,
        feature_key="screener",
        display_name="智能選股",
        tier=tier,
        status="active",
        enabled=True,
        allowed_tiers=["pro", "unlimited", "admin"],
        reason=reason,
    )


@pytest.fixture
def auth_on(reports):
    with patch("tools.screener_tool.settings", MagicMock(auth_required=True)):
        yield


def test_tier_without_screener_access_gets_no_list(auth_on):
    with patch(
        "tools.screener_tool.feature_access_service.check_feature_access",
        return_value=_access(False, "tier_not_allowed"),
    ) as check:
        out = _run()

    check.assert_called_once_with("screener", "u1")
    assert "只開放給 pro、unlimited、admin 方案" in out
    assert "free 方案" in out
    assert "建準" not in out
    assert "不要自行列出任何選股名單" in out


def test_suspended_account_gets_no_list(auth_on):
    with patch(
        "tools.screener_tool.feature_access_service.check_feature_access",
        return_value=_access(False, "account_suspended"),
    ):
        out = _run()

    assert "帳號已被停用" in out
    assert "建準" not in out


def test_allowed_tier_gets_the_list(auth_on):
    with patch(
        "tools.screener_tool.feature_access_service.check_feature_access",
        return_value=_access(True, tier="pro"),
    ):
        assert "建準" in _run()


def test_no_user_gets_no_list(auth_on):
    out = get_screener_picks.invoke({}, config=user_config(""))

    assert "需要登入" in out
    assert "建準" not in out
