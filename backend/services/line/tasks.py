"""Cloud Tasks enqueue — 把單一 LINE 事件交給 /api/line/process 另起 request 處理.

Task 帶著原始 webhook body 與 LINE 簽章，/process 會重新驗簽，
所以不需要額外的共用金鑰。
"""

import asyncio

from config import settings
from services.line.client import SIGNATURE_HEADER

EVENT_ID_HEADER = "X-Line-Event-Id"
DISPATCH_DEADLINE_SECONDS = 300
CREATE_TASK_TIMEOUT_SECONDS = 10

_client = None


def _get_client():
    global _client
    if _client is None:
        # 延後 import：只有真的要建 task 時才載入，不拖慢服務啟動
        from google.cloud import tasks_v2

        _client = tasks_v2.CloudTasksClient()
    return _client


def _create_task(raw_body: bytes, signature: str, event_id: str, target_url: str) -> None:
    from google.cloud import tasks_v2
    from google.protobuf import duration_pb2

    client = _get_client()
    parent = client.queue_path(
        settings.google_cloud_project,
        settings.line_tasks_location,
        settings.line_tasks_queue,
    )
    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=target_url,
            headers={
                "Content-Type": "application/json",
                SIGNATURE_HEADER: signature,
                EVENT_ID_HEADER: event_id,
            },
            body=raw_body,
        ),
        dispatch_deadline=duration_pb2.Duration(seconds=DISPATCH_DEADLINE_SECONDS),
    )
    client.create_task(parent=parent, task=task, timeout=CREATE_TASK_TIMEOUT_SECONDS)


async def enqueue_event(raw_body: bytes, signature: str, event_id: str, target_url: str) -> None:
    """Create one Cloud Task that will POST this webhook body to ``target_url``."""
    await asyncio.to_thread(_create_task, raw_body, signature, event_id, target_url)
