"""Tests for LINE event handling — LINE client, Firestore, quota and agent all mocked."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from config import settings
from services.line import handler
from services.quota_service import QuotaCheckResult

LINE_USER_ID = "U" + "a" * 32


def _event(text: str = "台積電現在多少", **overrides) -> dict:
    event = {
        "type": "message",
        "webhookEventId": "evt-1",
        "replyToken": "reply-token",
        "source": {"type": "user", "userId": LINE_USER_ID},
        "message": {"type": "text", "id": "1", "text": text},
    }
    event.update(overrides)
    return event


def _quota(allowed: bool = True, tier: str = "pro", reason: str | None = None) -> QuotaCheckResult:
    return QuotaCheckResult(
        allowed=allowed,
        tier=tier,
        daily_limit=100,
        used_today=1,
        remaining=99,
        reset_at=datetime.now(UTC),
        reason=reason,
    )


def _fake_agent(
    *chunks, calls: list | None = None, delay: float = 0, error: Exception | None = None
):
    async def _run_agent(question, conversation_id=None, user_id="", model_name=None):
        if calls is not None:
            calls.append(
                {
                    "question": question,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "model_name": model_name,
                }
            )
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        for chunk in chunks:
            yield chunk

    return _run_agent


@pytest.fixture
def env():
    with (
        patch.object(handler, "client") as client,
        patch.object(handler, "store") as store,
        patch.object(handler, "quota_service") as quota,
        patch.object(handler, "chat_limiter") as limiter,
        patch.object(handler, "accounts") as accounts,
    ):
        client.reply = AsyncMock(return_value=True)
        client.push = AsyncMock()
        client.log_push_usage = AsyncMock()
        client.start_loading = AsyncMock()
        store.claim_event.return_value = True
        store.try_acquire_inflight.return_value = True
        store.get_link.return_value = {"uid": "uid-1", "email": "me@example.com"}
        store.resolve_conversation.return_value = "conv-1"
        quota.check_and_consume.return_value = _quota()
        accounts.link_new_user.return_value = {"uid": "line_" + LINE_USER_ID, "email": ""}
        yield SimpleNamespace(
            client=client, store=store, quota=quota, limiter=limiter, accounts=accounts
        )


def _replied_texts(env) -> list[str]:
    return env.client.reply.call_args.args[1]


# ── events that never reach the agent ───────────────────────────────────────


async def test_duplicate_event_is_skipped(env):
    env.store.claim_event.return_value = False
    await handler.handle_event(_event())
    env.store.get_link.assert_not_called()
    env.client.reply.assert_not_called()


async def test_group_source_is_ignored(env):
    group_source = {"type": "group", "groupId": "G1", "userId": LINE_USER_ID}
    await handler.handle_event(_event(source=group_source))
    env.store.claim_event.assert_not_called()
    env.client.reply.assert_not_called()


async def test_unsupported_event_type_is_ignored(env):
    await handler.handle_event(_event(type="unfollow"))
    env.store.claim_event.assert_not_called()
    env.client.reply.assert_not_called()


async def test_new_user_is_given_an_account_and_answered(env):
    env.store.get_link.return_value = None
    calls: list = []

    with patch.object(handler, "run_agent", _fake_agent("答案", calls=calls)):
        await handler.handle_event(_event())

    env.accounts.link_new_user.assert_called_once_with(LINE_USER_ID)
    env.quota.check_and_consume.assert_called_once_with("line_" + LINE_USER_ID, email="")
    assert calls[0]["user_id"] == "line_" + LINE_USER_ID
    assert _replied_texts(env) == ["答案"]


async def test_new_user_adding_the_bot_gets_welcome(env):
    env.store.get_link.return_value = None

    await handler.handle_event(_event(type="follow"))

    env.accounts.link_new_user.assert_called_once_with(LINE_USER_ID)
    assert _replied_texts(env) == [handler.WELCOME_REPLY]


async def test_linked_user_is_not_given_a_new_account(env):
    with patch.object(handler, "run_agent", _fake_agent("答案")):
        await handler.handle_event(_event())
    env.accounts.link_new_user.assert_not_called()


async def test_account_creation_failure_sends_error_reply(env):
    env.store.get_link.return_value = None
    env.accounts.link_new_user.side_effect = RuntimeError("firebase down")

    await handler.handle_event(_event())

    assert _replied_texts(env) == [handler.ERROR_REPLY]
    env.quota.check_and_consume.assert_not_called()


async def test_follow_event_gets_welcome(env):
    await handler.handle_event(_event(type="follow"))
    assert _replied_texts(env) == [handler.WELCOME_REPLY]
    env.quota.check_and_consume.assert_not_called()


async def test_non_text_message_gets_text_only_reply(env):
    await handler.handle_event(_event(message={"type": "sticker", "id": "1"}))
    assert _replied_texts(env) == [handler.TEXT_ONLY_REPLY]
    env.quota.check_and_consume.assert_not_called()


@pytest.mark.parametrize("command", ["/new", "/NEW", " 新對話 "])
async def test_new_conversation_command_resets_without_using_quota(env, command):
    await handler.handle_event(_event(command))

    env.store.resolve_conversation.assert_called_once_with(
        LINE_USER_ID, env.store.get_link.return_value, force_new=True
    )
    assert _replied_texts(env) == [handler.NEW_CONVERSATION_REPLY]
    env.quota.check_and_consume.assert_not_called()
    env.client.start_loading.assert_not_called()


# ── limits ──────────────────────────────────────────────────────────────────


async def test_burst_limit_gets_polite_reply(env):
    env.limiter.check.side_effect = HTTPException(status_code=429, detail="Rate limit exceeded")
    await handler.handle_event(_event())
    env.limiter.check.assert_called_once_with("user:uid-1")
    assert _replied_texts(env) == [handler.RATE_LIMITED_REPLY]
    env.quota.check_and_consume.assert_not_called()


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("daily_quota_exceeded", handler.QUOTA_EXCEEDED_REPLY),
        ("account_suspended", handler.ACCOUNT_SUSPENDED_REPLY),
    ],
)
async def test_blocked_quota_is_logged_and_explained(env, reason, expected):
    env.quota.check_and_consume.return_value = _quota(allowed=False, tier="free", reason=reason)
    calls: list = []

    with patch.object(handler, "run_agent", _fake_agent("不該被呼叫", calls=calls)):
        await handler.handle_event(_event())

    assert calls == []
    assert _replied_texts(env) == [expected]
    log = env.quota.write_usage_log.call_args.kwargs
    assert log["blocked"] is True
    assert log["block_reason"] == reason


# ── answering ───────────────────────────────────────────────────────────────


async def test_happy_path_runs_agent_and_replies_plain_text(env):
    calls: list = []
    chunks = (
        {"type": "intent", "intent": "general", "ticker": None, "confidence": 0.9},
        "**台積電** 現價 ",
        {"type": "tool_start", "tool": "get_stock_price", "input": {}},
        "1,050 元",
        {"type": "citations", "citations": []},
    )

    with patch.object(handler, "run_agent", _fake_agent(*chunks, calls=calls)):
        await handler.handle_event(_event())

    env.client.start_loading.assert_awaited_once_with(LINE_USER_ID)
    env.quota.check_and_consume.assert_called_once_with("uid-1", email="me@example.com")
    assert calls == [
        {
            "question": "台積電現在多少",
            "conversation_id": "conv-1",
            "user_id": "uid-1",
            "model_name": settings.gemini_model_name,
        }
    ]
    env.client.reply.assert_awaited_once_with("reply-token", ["台積電 現價 1,050 元"])
    env.client.push.assert_not_called()
    env.client.log_push_usage.assert_not_called()
    env.store.try_acquire_inflight.assert_called_once_with(LINE_USER_ID)
    env.store.release_inflight.assert_called_once_with(LINE_USER_ID)

    log = env.quota.write_usage_log.call_args.kwargs
    assert log["endpoint"] == "/api/line/webhook"
    assert log["conversation_id"] == "conv-1"
    assert log["blocked"] is False


async def test_free_tier_uses_the_free_model(env):
    env.quota.check_and_consume.return_value = _quota(tier="free")
    calls: list = []

    with patch.object(handler, "run_agent", _fake_agent("答案", calls=calls)):
        await handler.handle_event(_event())

    assert calls[0]["model_name"] == settings.gemini_model_name_free


async def test_expired_reply_token_falls_back_to_push(env):
    env.client.reply.return_value = False

    with patch.object(handler, "run_agent", _fake_agent("答案")):
        await handler.handle_event(_event())

    env.client.push.assert_awaited_once_with(LINE_USER_ID, ["答案"])
    env.client.log_push_usage.assert_awaited_once()


# ── one question at a time per user ─────────────────────────────────────────


async def test_second_question_while_busy_is_told_to_wait(env):
    env.store.try_acquire_inflight.return_value = False
    env.client.reply.return_value = False  # reply token 已失效也不改用 push
    calls: list = []

    with patch.object(handler, "run_agent", _fake_agent("不該被呼叫", calls=calls)):
        await handler.handle_event(_event())

    assert calls == []
    assert _replied_texts(env) == [handler.BUSY_REPLY]
    env.client.push.assert_not_called()
    env.client.start_loading.assert_not_called()
    env.quota.check_and_consume.assert_not_called()
    env.store.release_inflight.assert_not_called()  # 鎖是第一題的，不能放


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(
            lambda env: setattr(env.quota.check_and_consume, "return_value", _quota(False)),
            id="quota-blocked",
        ),
        pytest.param(
            lambda env: setattr(
                env.limiter.check, "side_effect", HTTPException(status_code=429, detail="")
            ),
            id="rate-limited",
        ),
    ],
)
async def test_lock_released_on_early_return(env, setup):
    setup(env)
    with patch.object(handler, "run_agent", _fake_agent("答案")):
        await handler.handle_event(_event())
    env.store.release_inflight.assert_called_once_with(LINE_USER_ID)


async def test_lock_released_when_agent_fails(env):
    with patch.object(handler, "run_agent", _fake_agent(error=RuntimeError("vertex down"))):
        await handler.handle_event(_event())
    env.store.release_inflight.assert_called_once_with(LINE_USER_ID)
    assert _replied_texts(env) == [handler.ERROR_REPLY]


async def test_commands_do_not_take_the_lock(env):
    await handler.handle_event(_event("新對話"))
    await handler.handle_event(_event(type="follow"))
    env.store.try_acquire_inflight.assert_not_called()


async def test_agent_exception_sends_error_reply(env):
    with patch.object(handler, "run_agent", _fake_agent(error=RuntimeError("vertex down"))):
        await handler.handle_event(_event())
    assert _replied_texts(env) == [handler.ERROR_REPLY]


async def test_agent_timeout_sends_error_reply(env):
    with (
        patch.object(handler, "AGENT_TIMEOUT_SECONDS", 0.01),
        patch.object(handler, "run_agent", _fake_agent("太慢", delay=1)),
    ):
        await handler.handle_event(_event())
    assert _replied_texts(env) == [handler.ERROR_REPLY]


async def test_empty_answer_sends_error_reply(env):
    with patch.object(handler, "run_agent", _fake_agent()):
        await handler.handle_event(_event())
    assert _replied_texts(env) == [handler.ERROR_REPLY]


async def test_failed_delivery_does_not_raise(env):
    env.client.reply.side_effect = RuntimeError("LINE unreachable")
    with patch.object(handler, "run_agent", _fake_agent("答案")):
        await handler.handle_event(_event())
