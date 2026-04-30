"""Chat API — 與 Navi 對話（支援 SSE streaming + Agent tool-calling）."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.dependencies import verify_firebase_token
from api.rate_limit import chat_limiter, get_rate_limit_key
from models.schemas import ChatRequest
from services import quota_service
from services.agent_service import run_agent
from services.conversation_service import (
    delete_conversation,
    get_conversation_messages,
    list_conversations,
    new_conversation_id,
)
from services.firestore_client import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _get_uid(user: dict) -> str:
    return user.get("uid", "")


async def _sse_generator(
    question: str,
    conversation_id: str | None = None,
    user_id: str = "",
):
    """Wrap Agent streaming output in SSE format."""
    # Auto-generate conversation_id if not provided
    cid = conversation_id or new_conversation_id()

    # Send conversation_id as the first event so the client can track it
    meta = json.dumps({"conversation_id": cid}, ensure_ascii=False)
    yield f"data: {meta}\n\n"

    try:
        async for chunk in run_agent(question, conversation_id=cid, user_id=user_id):
            if isinstance(chunk, str):
                data = json.dumps({"text": chunk}, ensure_ascii=False)
            else:
                # ThinkingEvent dict — already contains "type" key
                data = json.dumps(chunk, ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("Error during agent analysis")
        error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"


@router.post("")
async def chat(
    request: ChatRequest,
    req: Request,
    user: dict = Depends(verify_firebase_token),
):
    """與 Navi 對話，回傳 SSE streaming response.

    - 首次對話不帶 conversation_id → 自動產生
    - 後續對話帶 conversation_id → 多輪延續
    """
    uid = _get_uid(user)
    email = user.get("email", "")
    display_name = user.get("name", "") or user.get("display_name", "")

    # Per-minute burst limiter (in-memory, fast)
    chat_limiter.check(get_rate_limit_key(req, user))

    # Daily quota check (Firestore-backed, atomic)
    quota = quota_service.check_and_consume(uid, email=email, display_name=display_name)
    if not quota.allowed:
        # Audit log: blocked
        quota_service.write_usage_log(
            uid=uid,
            email=email,
            tier=quota.tier,
            endpoint="/api/chat",
            conversation_id=request.conversation_id,
            question=request.message,
            blocked=True,
            block_reason=quota.reason,
        )
        message = (
            "帳號已被停用，請聯絡管理員。"
            if quota.reason == "account_suspended"
            else "今日訊息額度已用完，明日 00:00（台北時間）重置。"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "QUOTA_EXCEEDED" if quota.reason != "account_suspended" else "ACCOUNT_SUSPENDED",
                "message": message,
                "tier": quota.tier,
                "daily_limit": quota.daily_limit,
                "used_today": quota.used_today,
                "remaining": quota.remaining,
                "reset_at": quota.reset_at.isoformat(),
            },
        )

    # Audit log: allowed
    quota_service.write_usage_log(
        uid=uid,
        email=email,
        tier=quota.tier,
        endpoint="/api/chat",
        conversation_id=request.conversation_id,
        question=request.message,
        blocked=False,
    )

    response = StreamingResponse(
        _sse_generator(
            request.message,
            conversation_id=request.conversation_id,
            user_id=uid,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Quota-Tier": quota.tier,
            "X-Quota-Daily-Limit": str(quota.daily_limit),
            "X-Quota-Used": str(quota.used_today),
            "X-Quota-Remaining": str(quota.remaining),
            "X-Quota-Reset": quota.reset_at.isoformat(),
            "Access-Control-Expose-Headers": (
                "X-Request-ID, X-Quota-Tier, X-Quota-Daily-Limit, "
                "X-Quota-Used, X-Quota-Remaining, X-Quota-Reset"
            ),
        },
    )
    return response


# ── Conversation management ─────────────────────────────────────────────────


@router.get("/quota")
async def get_quota(user: dict = Depends(verify_firebase_token)):
    """取得目前使用者的今日額度狀態（不消耗）."""
    uid = _get_uid(user)
    email = user.get("email", "")
    display_name = user.get("name", "") or user.get("display_name", "")
    user_doc = quota_service.get_or_create_user(
        uid, email=email, display_name=display_name
    )
    tier = str(user_doc.get("tier", "free"))
    config = quota_service.get_quota_config(tier)
    daily_limit = quota_service._effective_daily_limit(user_doc, config)
    today = quota_service._today_str()
    db = get_db()
    snap = (
        db.collection(quota_service.USAGE_COUNTERS_COLLECTION)
        .document(quota_service._counter_doc_id(uid, today))
        .get()
    )
    used = int((snap.to_dict() or {}).get("chat_count", 0)) if snap.exists else 0
    remaining = -1 if daily_limit == -1 else max(0, daily_limit - used)
    return {
        "tier": tier,
        "status": user_doc.get("status", "active"),
        "daily_limit": daily_limit,
        "used_today": used,
        "remaining": remaining,
        "reset_at": quota_service._next_midnight_taipei().isoformat(),
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_history(
    conversation_id: str, user: dict = Depends(verify_firebase_token)
):
    """取得指定對話的訊息歷史."""
    messages = get_conversation_messages(conversation_id, user_id=_get_uid(user))
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"messages": messages}


@router.get("/conversations")
async def get_conversations(limit: int = 20, user: dict = Depends(verify_firebase_token)):
    """列出當前使用者最近的對話紀錄."""
    convs = list_conversations(user_id=_get_uid(user), limit=limit)
    return {"conversations": convs}


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str, user: dict = Depends(verify_firebase_token)):
    """刪除指定對話（僅限本人）."""
    deleted = delete_conversation(conversation_id, user_id=_get_uid(user))
    return {"deleted": deleted, "conversation_id": conversation_id}
