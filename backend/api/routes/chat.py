"""Chat API — 與 Navi 對話（支援 SSE streaming + Agent tool-calling）."""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.dependencies import verify_firebase_token
from models.schemas import ChatRequest
from services.agent_service import run_agent
from services.conversation_service import (
    delete_conversation,
    list_conversations,
    new_conversation_id,
)

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
    # just  test trigger
    cid = conversation_id or new_conversation_id()

    # Send conversation_id as the first event so the client can track it
    meta = json.dumps({"conversation_id": cid}, ensure_ascii=False)
    yield f"data: {meta}\n\n"

    try:
        async for chunk in run_agent(question, conversation_id=cid, user_id=user_id):
            data = json.dumps({"text": chunk}, ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("Error during agent analysis")
        error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"


@router.post("")
async def chat(request: ChatRequest, user: dict = Depends(verify_firebase_token)):
    """與 Navi 對話，回傳 SSE streaming response.

    - 首次對話不帶 conversation_id → 自動產生
    - 後續對話帶 conversation_id → 多輪延續
    """
    return StreamingResponse(
        _sse_generator(
            request.message,
            conversation_id=request.conversation_id,
            user_id=_get_uid(user),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Conversation management ─────────────────────────────────────────────────


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
