"""工具拿到的 uid 一定來自後端，模型無法指定；選股證據揭露由程式補上."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from services import agent_service
from services.screener.evidence import get_evidence
from tests.scripted_model import ScriptedModel
from tools.portfolio_tool import get_portfolio
from tools.runtime import user_config


def _empty_portfolio():
    return MagicMock(holdings_count=0)


def test_portfolio_schema_has_no_user_parameter():
    assert get_portfolio.tool_call_schema.model_json_schema()["properties"] == {}


def test_portfolio_reads_the_injected_user():
    with patch("tools.portfolio_tool.get_portfolio_summary", return_value=_empty_portfolio()) as s:
        get_portfolio.invoke({"user_id": "victim"}, config=user_config("owner"))

    s.assert_called_once_with("owner")


def test_portfolio_without_user_skips_the_lookup():
    with patch("tools.portfolio_tool.get_portfolio_summary") as summary:
        out = get_portfolio.invoke({}, config=user_config(""))

    summary.assert_not_called()
    assert "未提供 user_id" in out


async def test_agent_mode_injects_the_signed_in_user_even_if_the_model_names_another():
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_portfolio", "args": {"user_id": "victim"}, "id": "call_1"}
                ],
            ),
            AIMessage(content="你目前沒有持股。"),
        ]
    )

    with patch("tools.portfolio_tool.get_portfolio_summary", return_value=_empty_portfolio()) as s:
        chunks = [
            chunk
            async for chunk in agent_service._run_agent_mode(
                "我的持股", "portfolio", model, conversation_id=None, user_id="owner"
            )
        ]

    s.assert_called_once_with("owner")
    assert any(isinstance(c, dict) and c.get("tool") == "get_portfolio" for c in chunks)
    assert "你目前沒有持股。" in "".join(c for c in chunks if isinstance(c, str))


async def test_prefetch_injects_the_signed_in_user():
    with patch("tools.portfolio_tool.get_portfolio_summary", return_value=_empty_portfolio()) as s:
        _, calls = await agent_service._prefetch_tool_results(
            "2330", ["get_portfolio"], user_id="owner"
        )

    s.assert_called_once_with("owner")
    assert calls[0]["input"] == {}


def test_agent_prompt_does_not_carry_the_uid():
    prompt = agent_service._build_agent_system_prompt("portfolio")

    assert "user_id" not in prompt
    assert "<context>" not in prompt


def _screener_call(output):
    return {"name": "get_screener_picks", "input": {}, "output": output}


def test_disclosure_added_when_answer_drops_the_evidence_headline():
    headline = get_evidence("momentum")["headline"]

    added = agent_service._missing_screener_disclosure(
        "這週動能策略選了帆宣。", [_screener_call(f"名單…\n🔎 策略證據：{headline}")]
    )

    assert added == f"\n\n🔎 策略證據\n・動能策略：{headline}"


def test_disclosure_only_for_profiles_the_tool_returned():
    value_headline = get_evidence("value")["headline"]

    added = agent_service._missing_screener_disclosure(
        "價值策略選了建準。", [_screener_call(f"🔎 策略證據：{value_headline}")]
    )

    assert value_headline in added
    assert get_evidence("momentum")["headline"] not in added


def test_no_disclosure_when_answer_quotes_it():
    headline = get_evidence("momentum")["headline"]

    assert (
        agent_service._missing_screener_disclosure(
            f"策略證據：{headline}", [_screener_call(f"🔎 策略證據：{headline}")]
        )
        == ""
    )


def test_no_disclosure_without_screener_results():
    assert agent_service._missing_screener_disclosure("台積電技術面…", []) == ""
    assert (
        agent_service._missing_screener_disclosure("沒有權限", [_screener_call("⚠️ 只開放給 pro")])
        == ""
    )
