"""LINE API — Messaging API webhook 與 Cloud Tasks 的處理端點.

LINE 要求 webhook 約 2 秒內回 200，但 Agent 一題要跑數十秒，而 Cloud Run
回完 response 後 CPU 會被降速。所以 /webhook 只驗簽並把事件丟進 Cloud Tasks，
由 Cloud Tasks 另起一個 request 打 /process 來真正跑 Agent。
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request, status

from config import settings
from services.line.client import SIGNATURE_HEADER, verify_signature
from services.line.handler import handle_event
from services.line.tasks import EVENT_ID_HEADER, enqueue_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/line", tags=["line"])

# asyncio 只保留 task 的弱參考；本機 fallback 的背景 task 要自己留住，否則可能被回收
_background_tasks: set[asyncio.Task] = set()


def _parse_signed_events(body: bytes, signature: str | None) -> list[dict]:
    """Verify the LINE signature over the raw body and return its events.

    若未設定 LINE_CHANNEL_SECRET，視為未啟用（拒絕所有呼叫）。
    """
    channel_secret = settings.line_channel_secret
    if not channel_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LINE webhook is not configured (LINE_CHANNEL_SECRET missing).",
        )
    if not verify_signature(body, signature, channel_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LINE signature."
        )
    try:
        events = json.loads(body).get("events", [])
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook body."
        ) from exc
    return [event for event in events if isinstance(event, dict)]


@router.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
):
    """LINE Messaging API webhook：驗簽後把每個事件排入處理，立刻回 200."""
    body = await request.body()
    events = _parse_signed_events(body, x_line_signature)

    use_queue = bool(settings.line_tasks_queue)
    if not use_queue and os.environ.get("K_SERVICE"):
        # 在 Cloud Run 上行程內背景處理會因 CPU 降速而卡住，寧可明確失敗
        logger.error("LINE_TASKS_QUEUE is not set on Cloud Run; refusing to process in-process")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LINE task queue is not configured (LINE_TASKS_QUEUE missing).",
        )

    target_url = f"https://{request.headers.get('host', '')}/api/line/process"
    for event in events:
        event_id = event.get("webhookEventId")
        if not event_id:
            continue
        if use_queue:
            try:
                await enqueue_event(body, x_line_signature or "", event_id, target_url)
            except Exception as exc:
                # 回 5xx 讓 LINE 重送；已排入的事件靠 webhookEventId 去重
                logger.exception("Failed to enqueue LINE event %s", event_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to enqueue event.",
                ) from exc
        else:
            task = asyncio.create_task(handle_event(event))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

    return {"status": "ok"}


@router.post("/process")
async def process(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    x_line_event_id: str | None = Header(default=None, alias=EVENT_ID_HEADER),
):
    """Cloud Tasks 的目標：處理 webhook body 中 X-Line-Event-Id 指定的那個事件.

    Auth：重新驗證 LINE 簽章。這個端點只接受 LINE 簽過的 body，
    信任邊界與公開的 /webhook 相同。
    """
    body = await request.body()
    events = _parse_signed_events(body, x_line_signature)

    event = next((e for e in events if e.get("webhookEventId") == x_line_event_id), None)
    if event is None:
        logger.warning("LINE event %s not found in task body", x_line_event_id)
        return {"status": "ignored"}

    # handle_event 不會丟例外；一律回 200，避免 Cloud Tasks 重跑做到一半的事件
    await handle_event(event)
    return {"status": "ok"}
