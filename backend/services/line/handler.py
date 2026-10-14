"""LINE 事件處理 — 把一則 LINE 訊息接到既有的 Agent pipeline."""

import asyncio
import logging

from fastapi import HTTPException

from api.rate_limit import chat_limiter
from config import model_for_tier
from services import conversation_service, portfolio_changes, quota_service
from services.agent_service import AgentExtras, AgentImage, run_agent
from services.line import LINE_ONLY_RETENTION_DAYS, accounts, client, is_line_only_uid, store
from services.line import portfolio as line_portfolio
from services.line.formatting import format_for_line

logger = logging.getLogger(__name__)

ENDPOINT = "/api/line/webhook"
AGENT_TIMEOUT_SECONDS = 240
NEW_CONVERSATION_COMMANDS = {"/new", "新對話"}
DELETE_HISTORY_COMMANDS = {"/delete", "刪除紀錄"}
# 只有在真的有待確認的持股變更時才攔下來，否則當一般訊息交給 agent
CONFIRM_COMMANDS = {"/confirm", "確認"}
CANCEL_COMMANDS = {"/cancel", "取消"}

WELCOME_REPLY = (
    "嗨，我是 Navi 🧚\n"
    "直接輸入問題就可以開始，例如「台積電現在的技術面如何？」\n"
    "也可以記錄持股：說「今天買 1 張台積電 600」，或傳券商的庫存截圖，"
    "我整理成清單後，你回「確認」才會寫入。\n"
    "輸入「新對話」可以重新開始。\n"
    "\n"
    "🔒 隱私\n"
    "・你問的內容不會顯示在管理後台\n"
    f"・每段對話在最後一次使用 {LINE_ONLY_RETENTION_DAYS} 天後自動刪除\n"
    "・輸入「刪除紀錄」可以立即刪除\n"
    "・問題和圖片會交給 Google 的 Gemini 模型回答，圖片不會保存"
)
TEXT_ONLY_REPLY = "目前只支援文字和圖片訊息，請直接輸入你的問題。"
IMAGE_FAILED_REPLY = "圖片下載失敗，請再傳一次。"
CONFIRM_BUSY_REPLY = "上一題還在處理中，請等回覆後再確認。"
PENDING_EXPIRED_REPLY = (
    "這份清單已經過期（超過 {minutes} 分鐘），持股沒有變動。請重新告訴我要記錄什麼。"
)
PENDING_CANCELLED_REPLY = "已取消，持股沒有變動。"
BUSY_REPLY = "上一題還在處理中，請等回覆後再問下一題。"
DELETE_BUSY_REPLY = "上一題還在處理中，請等回覆後再刪除紀錄。"
NEW_CONVERSATION_REPLY = "已開始新對話，請輸入你的問題。"
DELETE_ALL_REPLY = "已刪除你的全部對話紀錄（{count} 段）。"
DELETE_CURRENT_REPLY = "已刪除目前這段對話。網頁版的其他對話請到網頁上刪除。"
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


async def _run_agent_text(
    question: str,
    conversation_id: str,
    uid: str,
    model_name: str,
    *,
    extras: AgentExtras | None = None,
    images: list[AgentImage] | None = None,
) -> str:
    """Run the agent to completion and return the text answer.

    必須把 generator 跑完：對話記錄是在最後一次 yield 之後才寫入的。
    """
    parts: list[str] = []
    async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
        async for chunk in run_agent(
            question,
            conversation_id=conversation_id,
            user_id=uid,
            model_name=model_name,
            extras=extras,
            images=images,
        ):
            if isinstance(chunk, str):
                parts.append(chunk)
    return "".join(parts)


async def _answer_question(
    question: str,
    reply_token: str,
    line_user_id: str,
    link: dict,
    *,
    image_message_id: str | None = None,
) -> None:
    """同一人同時只處理一題：第二題直接請他等，不排隊、不計額度."""
    if not await asyncio.to_thread(store.try_acquire_inflight, line_user_id):
        # 這則提醒不值得花 push 則數
        await _send(reply_token, line_user_id, [BUSY_REPLY], allow_push=False)
        return
    try:
        await _answer_question_locked(
            question, reply_token, line_user_id, link, image_message_id=image_message_id
        )
    finally:
        await asyncio.to_thread(store.release_inflight, line_user_id)


async def _discard_pending(line_user_id: str, link: dict) -> None:
    """使用者傳了別的訊息，上一份待確認清單就作廢."""
    if not link.get(store.PENDING_PORTFOLIO_FIELD):
        return
    try:
        await asyncio.to_thread(store.discard_pending_portfolio, line_user_id)
    except Exception:
        logger.warning("Failed to discard pending portfolio change", exc_info=True)


async def _answer_question_locked(
    question: str,
    reply_token: str,
    line_user_id: str,
    link: dict,
    *,
    image_message_id: str | None = None,
) -> None:
    uid = link["uid"]
    email = link.get("email", "")

    await _discard_pending(line_user_id, link)
    # 等 loading API 回應後才繼續：若回覆比它早到，動畫會掛滿整段時間
    await client.start_loading(line_user_id)
    conversation_id = await asyncio.to_thread(store.resolve_conversation, line_user_id, link)

    try:
        chat_limiter.check(f"user:{uid}")
    except HTTPException:
        await _send(reply_token, line_user_id, [RATE_LIMITED_REPLY])
        return

    images: list[AgentImage] | None = None
    if image_message_id:
        # 在扣額度之前下載：下載失敗不該算一題
        content = await client.get_message_content(image_message_id)
        if content is None:
            await _send(reply_token, line_user_id, [IMAGE_FAILED_REPLY])
            return
        images = [AgentImage(data=content[0], mime_type=content[1])]

    quota = await asyncio.to_thread(quota_service.check_and_consume, uid, email=email)
    await asyncio.to_thread(
        quota_service.write_usage_log,
        uid=uid,
        email=email,
        tier=quota.tier,
        endpoint=ENDPOINT,
        conversation_id=conversation_id,
        blocked=not quota.allowed,
        block_reason=None if quota.allowed else quota.reason,
    )
    if not quota.allowed:
        message = (
            ACCOUNT_SUSPENDED_REPLY if quota.reason == "account_suspended" else QUOTA_EXCEEDED_REPLY
        )
        await _send(reply_token, line_user_id, [message])
        return

    answer = await _run_agent_text(
        question,
        conversation_id,
        uid,
        model_for_tier(quota.tier),
        extras=line_portfolio.agent_extras(line_user_id),
        images=images,
    )
    await _send(reply_token, line_user_id, format_for_line(answer) or [ERROR_REPLY])


async def _confirm_portfolio(reply_token: str, line_user_id: str, link: dict) -> None:
    """寫入待確認的持股變更；不經過模型，也不計額度."""
    # 跟提問共用同一把鎖：題目跑到一半可能正在換一份新清單
    if not await asyncio.to_thread(store.try_acquire_inflight, line_user_id):
        await _send(reply_token, line_user_id, [CONFIRM_BUSY_REPLY], allow_push=False)
        return
    try:
        pending = await asyncio.to_thread(store.take_pending_portfolio, line_user_id)
        if pending is None:
            message = PENDING_EXPIRED_REPLY.format(minutes=store.PENDING_PORTFOLIO_MINUTES)
        else:
            message = await asyncio.to_thread(
                portfolio_changes.apply, link["uid"], pending["kind"], pending["items"]
            )
    finally:
        await asyncio.to_thread(store.release_inflight, line_user_id)
    await _send(reply_token, line_user_id, [message])


async def _cancel_portfolio(reply_token: str, line_user_id: str) -> None:
    await asyncio.to_thread(store.discard_pending_portfolio, line_user_id)
    await _send(reply_token, line_user_id, [PENDING_CANCELLED_REPLY])


async def _delete_history(reply_token: str, line_user_id: str, link: dict) -> None:
    """LINE-only 帳號刪掉全部對話；綁網頁帳號的只刪目前這段，網頁上的紀錄不動."""
    # 和提問共用同一把鎖：題目跑到一半就刪，跑完寫入紀錄時會把對話建回來
    if not await asyncio.to_thread(store.try_acquire_inflight, line_user_id):
        await _send(reply_token, line_user_id, [DELETE_BUSY_REPLY], allow_push=False)
        return
    try:
        uid = link["uid"]
        if is_line_only_uid(uid):
            count = await asyncio.to_thread(conversation_service.delete_all_conversations, uid)
            message = DELETE_ALL_REPLY.format(count=count)
        else:
            if link.get("conversation_id"):
                await asyncio.to_thread(
                    conversation_service.delete_conversation, link["conversation_id"], user_id=uid
                )
            message = DELETE_CURRENT_REPLY
        await asyncio.to_thread(store.resolve_conversation, line_user_id, link, force_new=True)
    finally:
        await asyncio.to_thread(store.release_inflight, line_user_id)
    await _send(reply_token, line_user_id, [message])


async def _handle_linked_user(event: dict, reply_token: str, line_user_id: str, link: dict) -> None:
    if event.get("type") == "follow":
        await _send(reply_token, line_user_id, [WELCOME_REPLY])
        return

    message = event.get("message") or {}
    if message.get("type") == "image":
        await _answer_question(
            "", reply_token, line_user_id, link, image_message_id=message.get("id")
        )
        return
    if message.get("type") != "text":
        await _send(reply_token, line_user_id, [TEXT_ONLY_REPLY])
        return

    text = (message.get("text") or "").strip()
    if not text:
        return
    if link.get(store.PENDING_PORTFOLIO_FIELD):
        if text.lower() in CONFIRM_COMMANDS:
            await _confirm_portfolio(reply_token, line_user_id, link)
            return
        if text.lower() in CANCEL_COMMANDS:
            await _cancel_portfolio(reply_token, line_user_id)
            return
    if text.lower() in NEW_CONVERSATION_COMMANDS:
        await asyncio.to_thread(store.resolve_conversation, line_user_id, link, force_new=True)
        await _send(reply_token, line_user_id, [NEW_CONVERSATION_REPLY])
        return
    if text.lower() in DELETE_HISTORY_COMMANDS:
        await _delete_history(reply_token, line_user_id, link)
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
