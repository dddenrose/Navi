"""LINE 事件處理 — 把一則 LINE 訊息接到既有的 Agent pipeline."""

import asyncio
import logging

from fastapi import HTTPException

from api.rate_limit import chat_limiter
from config import model_for_tier
from services import quota_service
from services.agent_service import run_agent
from services.line import accounts, client, store
from services.line.formatting import format_for_line

logger = logging.getLogger(__name__)

ENDPOINT = "/api/line/webhook"
AGENT_TIMEOUT_SECONDS = 240
NEW_CONVERSATION_COMMANDS = {"/new", "新對話"}

WELCOME_REPLY = (
    "嗨，我是 Navi 🧚\n"
    "直接輸入問題就可以開始，例如「台積電現在的技術面如何？」\n"
    "輸入「新對話」可以重新開始。"
)
TEXT_ONLY_REPLY = "目前只支援文字訊息，請直接輸入你的問題。"
BUSY_REPLY = "上一題還在處理中，請等回覆後再問下一題。"
NEW_CONVERSATION_REPLY = "已開始新對話，請輸入你的問題。"
RATE_LIMITED_REPLY = "訊息太頻繁了，請稍等一分鐘再試。"
QUOTA_EXCEEDED_REPLY = "今日訊息額度已用完，明日 00:00（台北時間）重置。"
ACCOUNT_SUSPENDED_REPLY = "帳號已被停用，請聯絡管理員。"
ERROR_REPLY = "抱歉，分析過程中發生錯誤，請稍後再試。"


async def _send(
    reply_token: str, line_user_id: str, texts: list[str], *, allow_push: bool = True
) -> None:
    """Reply（免費）優先；reply token 失效時才改用 push（計入每月則數）."""
    if reply_token and await client.reply(reply_token, texts):
        return
    if allow_push:
        await client.push(line_user_id, texts)
        await client.log_push_usage()


async def _run_agent_text(question: str, conversation_id: str, uid: str, model_name: str) -> str:
    """Run the agent to completion and return the text answer.

    必須把 generator 跑完：對話記錄是在最後一次 yield 之後才寫入的。
    """
    parts: list[str] = []
    async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
        async for chunk in run_agent(
            question, conversation_id=conversation_id, user_id=uid, model_name=model_name
        ):
            if isinstance(chunk, str):
                parts.append(chunk)
    return "".join(parts)


async def _answer_question(question: str, reply_token: str, line_user_id: str, link: dict) -> None:
    """同一人同時只處理一題：第二題直接請他等，不排隊、不計額度."""
    if not await asyncio.to_thread(store.try_acquire_inflight, line_user_id):
        # 這則提醒不值得花 push 則數
        await _send(reply_token, line_user_id, [BUSY_REPLY], allow_push=False)
        return
    try:
        await _answer_question_locked(question, reply_token, line_user_id, link)
    finally:
        await asyncio.to_thread(store.release_inflight, line_user_id)


async def _answer_question_locked(
    question: str, reply_token: str, line_user_id: str, link: dict
) -> None:
    uid = link["uid"]
    email = link.get("email", "")

    # 等 loading API 回應後才繼續：若回覆比它早到，動畫會掛滿整段時間
    await client.start_loading(line_user_id)
    conversation_id = await asyncio.to_thread(store.resolve_conversation, line_user_id, link)

    try:
        chat_limiter.check(f"user:{uid}")
    except HTTPException:
        await _send(reply_token, line_user_id, [RATE_LIMITED_REPLY])
        return

    quota = await asyncio.to_thread(quota_service.check_and_consume, uid, email=email)
    await asyncio.to_thread(
        quota_service.write_usage_log,
        uid=uid,
        email=email,
        tier=quota.tier,
        endpoint=ENDPOINT,
        conversation_id=conversation_id,
        question=question,
        blocked=not quota.allowed,
        block_reason=None if quota.allowed else quota.reason,
    )
    if not quota.allowed:
        message = (
            ACCOUNT_SUSPENDED_REPLY if quota.reason == "account_suspended" else QUOTA_EXCEEDED_REPLY
        )
        await _send(reply_token, line_user_id, [message])
        return

    answer = await _run_agent_text(question, conversation_id, uid, model_for_tier(quota.tier))
    await _send(reply_token, line_user_id, format_for_line(answer) or [ERROR_REPLY])


async def _handle_linked_user(event: dict, reply_token: str, line_user_id: str, link: dict) -> None:
    if event.get("type") == "follow":
        await _send(reply_token, line_user_id, [WELCOME_REPLY])
        return

    message = event.get("message") or {}
    if message.get("type") != "text":
        await _send(reply_token, line_user_id, [TEXT_ONLY_REPLY])
        return

    text = (message.get("text") or "").strip()
    if not text:
        return
    if text.lower() in NEW_CONVERSATION_COMMANDS:
        await asyncio.to_thread(store.resolve_conversation, line_user_id, link, force_new=True)
        await _send(reply_token, line_user_id, [NEW_CONVERSATION_REPLY])
        return

    await _answer_question(text, reply_token, line_user_id, link)


async def handle_event(event: dict) -> None:
    """Handle one LINE webhook event end to end. Never raises."""
    event_id = event.get("webhookEventId", "")
    try:
        if event.get("type") not in ("message", "follow"):
            return
        source = event.get("source") or {}
        line_user_id = source.get("userId", "")
        # 只服務一對一聊天；群組與多人聊天室一律忽略
        if source.get("type") != "user" or not line_user_id:
            return
        if event_id and not await asyncio.to_thread(store.claim_event, event_id):
            logger.info("LINE event %s already handled, skipped", event_id)
            return

        reply_token = event.get("replyToken", "")
        link = await asyncio.to_thread(store.get_link, line_user_id)
    except Exception:
        logger.exception("LINE event %s failed before reaching the user flow", event_id)
        return

    try:
        if not link or not link.get("uid"):
            # 第一次找 bot 的人自動開通；停用與額度在管理後台控制
            link = await asyncio.to_thread(accounts.link_new_user, line_user_id)
        await _handle_linked_user(event, reply_token, line_user_id, link)
    except Exception:
        logger.exception("LINE event %s failed", event_id)
        try:
            await _send(reply_token, line_user_id, [ERROR_REPLY])
        except Exception:
            logger.exception("LINE event %s: could not deliver the error reply", event_id)
