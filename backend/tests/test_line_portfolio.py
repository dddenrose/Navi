"""LINE 記錄持股：工具只建立待確認清單、清單一定原樣出現在回覆、圖片送進模型."""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from services import agent_service, portfolio_changes
from services.agent_service import AgentImage
from services.line import portfolio as line_portfolio
from tests.scripted_model import ScriptedModel
from tools import ALL_TOOLS
from tools import line_portfolio_tool as tool_module
from tools.line_portfolio_tool import propose_set_holdings, propose_trades, required_blocks
from tools.runtime import user_config

LINE_USER_ID = "U" + "b" * 32
TRADE = {"stock": "台積電", "action": "buy", "quantity": 2, "unit": "張", "price": 600}


@pytest.fixture
def env():
    with (
        patch.object(tool_module.portfolio_service, "list_holdings", return_value=[]) as holdings,
        patch.object(tool_module, "store") as store,
        patch.object(portfolio_changes, "normalize_ticker", return_value="2330.TW"),
        patch.object(
            portfolio_changes, "search_tw_stocks", return_value=[{"code": "2330", "name": "台積電"}]
        ),
    ):
        store.PENDING_PORTFOLIO_MINUTES = 10
        yield holdings, store


def _config(line_user_id: str = LINE_USER_ID):
    return user_config("uid-1", line_user_id=line_user_id)


# ── tools ───────────────────────────────────────────────────────────────────


def test_model_cannot_see_or_set_who_the_change_is_for():
    for tool in (propose_trades, propose_set_holdings):
        schema = tool.tool_call_schema.model_json_schema()
        assert list(schema["properties"]) in (["trades"], ["holdings"])


def test_write_tools_are_not_given_to_the_web_chat():
    assert not {t.name for t in ALL_TOOLS} & tool_module.PROPOSAL_TOOL_NAMES


def test_proposal_is_saved_not_written(env):
    holdings, store = env

    out = propose_trades.invoke({"trades": [TRADE]}, config=_config())

    holdings.assert_called_once_with("uid-1")
    line_user_id, kind, items = store.save_pending_portfolio.call_args.args
    assert (line_user_id, kind) == (LINE_USER_ID, portfolio_changes.TRADES)
    assert items[0]["shares"] == 2000
    assert out.startswith(portfolio_changes.SUMMARY_HEADER)
    assert "不要說已經記錄完成" in out


def test_invalid_proposal_saves_nothing(env):
    _, store = env

    out = propose_trades.invoke({"trades": [{**TRADE, "price": 0}]}, config=_config())

    store.save_pending_portfolio.assert_not_called()
    assert out.startswith("⚠️ 沒有建立待確認清單")
    assert "第 1 筆：價格必須大於 0" in out


def test_outside_line_nothing_is_saved(env):
    _, store = env

    out = propose_trades.invoke({"trades": [TRADE]}, config=_config(line_user_id=""))

    store.save_pending_portfolio.assert_not_called()
    assert "只能在 LINE" in out


def test_firestore_error_says_nothing_was_recorded(env):
    holdings, store = env
    holdings.side_effect = RuntimeError("firestore down")

    out = propose_trades.invoke({"trades": [TRADE]}, config=_config())

    store.save_pending_portfolio.assert_not_called()
    assert "不要說已經記錄" in out


def test_set_holdings_proposal(env):
    _, store = env
    row = {"stock": "2330", "quantity": 2000, "unit": "股", "avg_cost": 598.5}

    out = propose_set_holdings.invoke({"holdings": [row]}, config=_config())

    assert store.save_pending_portfolio.call_args.args[1] == portfolio_changes.HOLDINGS
    assert "台積電（2330）新增 2,000 股（2 張），均價 598.5 元" in out


def test_required_block_is_the_last_list_without_the_note_to_the_model(env):
    first = propose_trades.invoke({"trades": [TRADE]}, config=_config())
    second = propose_trades.invoke({"trades": [{**TRADE, "quantity": 3}]}, config=_config())
    failed = propose_trades.invoke({"trades": [{**TRADE, "price": 0}]}, config=_config())
    calls = [
        {"name": "propose_trades", "output": first},
        {"name": "propose_trades", "output": second},
        {"name": "propose_trades", "output": failed},
        {"name": "get_stock_price", "output": portfolio_changes.SUMMARY_HEADER},
    ]

    blocks = required_blocks(calls)

    assert len(blocks) == 1
    assert "3,000 股" in blocks[0]
    assert "給你的說明" not in blocks[0]
    assert blocks[0].endswith(portfolio_changes.CONFIRM_HINT)


def test_extras_carry_todays_date_and_the_line_user():
    extras = line_portfolio.agent_extras(LINE_USER_ID)

    assert extras.tool_context == {"line_user_id": LINE_USER_ID}
    assert portfolio_changes.today_taipei().isoformat() in extras.instructions
    assert extras.required_blocks is required_blocks


# ── agent integration ───────────────────────────────────────────────────────


async def _run(model, *, images=None, extras=None) -> str:
    chunks = [
        c
        async for c in agent_service._run_agent_mode(
            "今天買了 2 張台積電 600",
            "portfolio_update",
            model,
            conversation_id=None,
            user_id="uid-1",
            extras=extras or line_portfolio.agent_extras(LINE_USER_ID),
            images=images,
        )
    ]
    return "".join(c for c in chunks if isinstance(c, str))


async def test_list_is_appended_when_the_model_leaves_it_out(env):
    _, store = env
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "propose_trades", "args": {"trades": [TRADE]}, "id": "c1"}],
            ),
            AIMessage(content="好的，我幫你記好了！"),
        ]
    )

    answer = await _run(model)

    # 模型以為記好了，但使用者一定看得到要確認的清單
    assert store.save_pending_portfolio.call_args.args[0] == LINE_USER_ID
    assert portfolio_changes.SUMMARY_HEADER in answer
    assert "買進 台積電（2330）2,000 股（2 張）× 600 元" in answer
    assert portfolio_changes.CONFIRM_HINT in answer


async def test_list_is_not_repeated_when_the_model_quotes_it(env):
    tool_output = propose_trades.invoke({"trades": [TRADE]}, config=_config())
    summary = tool_output.split("\n\n（給你的說明")[0]
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "propose_trades", "args": {"trades": [TRADE]}, "id": "c1"}],
            ),
            # 模型改了換行，內容一樣
            AIMessage(content="請核對：\n" + summary.replace("\n", "\n\n")),
        ]
    )

    answer = await _run(model)

    assert answer.count(portfolio_changes.SUMMARY_HEADER) == 1


async def test_image_reaches_the_model_and_only_a_marker_is_kept():
    model = ScriptedModel(responses=[AIMessage(content="這是一張 K 線圖")])
    image = AgentImage(data=b"\x89PNG", mime_type="image/png")

    with patch.object(agent_service, "save_history") as save:
        chunks = [
            c
            async for c in agent_service._run_agent_mode(
                "這張圖怎麼看",
                "image",
                model,
                conversation_id="conv-1",
                user_id="uid-1",
                images=[image],
            )
        ]

    human = model.seen[0][-1]
    assert human.content[0] == {"type": "text", "text": "這張圖怎麼看"}
    assert human.content[1]["image_url"]["url"] == "data:image/png;base64,iVBORw=="
    assert "這是一張 K 線圖" in "".join(c for c in chunks if isinstance(c, str))
    assert save.call_args.args[1] == "[圖片] 這張圖怎麼看"


async def test_image_without_text_gets_a_placeholder_question():
    message = agent_service._human_message("", [AgentImage(b"x", "image/jpeg")])
    assert message.content[0]["text"] == agent_service._IMAGE_ONLY_TEXT
    assert agent_service._history_question("", [AgentImage(b"x", "image/jpeg")]) == "[圖片]"


async def test_run_agent_with_an_image_skips_classification_and_prefetch():
    model = ScriptedModel(responses=[AIMessage(content="ok")])

    with (
        patch.object(agent_service, "_build_llm", return_value=model),
        patch.object(agent_service, "_classify_intent_hybrid") as classify,
    ):
        chunks = [
            c
            async for c in agent_service.run_agent(
                "", user_id="uid-1", images=[AgentImage(b"x", "image/png")]
            )
        ]

    classify.assert_not_called()
    assert chunks[0]["intent"] == "image"
    assert "ok" in chunks


def test_missing_required_blocks():
    block = "📝 清單\n1. 買進"
    assert agent_service._missing_required_blocks("回覆", [block]) == f"\n\n{block}"
    assert agent_service._missing_required_blocks("📝 清單 1. 買進", [block]) == ""
    assert agent_service._missing_required_blocks("回覆", []) == ""
