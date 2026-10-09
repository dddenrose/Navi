"""Tests for the Cloud Tasks enqueue — task shape only (client mocked, no network)."""

from unittest.mock import MagicMock, patch

from google.cloud import tasks_v2

from services.line import tasks


@patch("services.line.tasks.settings")
async def test_enqueue_event_creates_signed_http_task(mock_settings):
    mock_settings.google_cloud_project = "navi-test"
    mock_settings.line_tasks_location = "asia-east1"
    mock_settings.line_tasks_queue = "line-events"
    client = MagicMock()
    client.queue_path.side_effect = tasks_v2.CloudTasksClient.queue_path
    body = '{"events":[{"webhookEventId":"evt-1","message":{"text":"台積電"}}]}'.encode()

    with patch("services.line.tasks._get_client", return_value=client):
        await tasks.enqueue_event(body, "sig==", "evt-1", "https://navi.example/api/line/process")

    kwargs = client.create_task.call_args.kwargs
    assert kwargs["parent"] == "projects/navi-test/locations/asia-east1/queues/line-events"
    task = kwargs["task"]
    assert task.name == ""  # 不命名：去重交給 line_events，不靠 task name
    assert task.http_request.http_method == tasks_v2.HttpMethod.POST
    assert task.http_request.url == "https://navi.example/api/line/process"
    assert task.http_request.body == body
    assert dict(task.http_request.headers) == {
        "Content-Type": "application/json",
        "X-Line-Signature": "sig==",
        "X-Line-Event-Id": "evt-1",
    }
    assert task.dispatch_deadline.seconds == tasks.DISPATCH_DEADLINE_SECONDS
