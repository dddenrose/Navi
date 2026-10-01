"""Tests for LINE API routes — signature auth + enqueue/dispatch contracts."""

import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

SECRET = "test-secret"


def _event(event_id: str, text: str = "台積電現在多少") -> dict:
    return {
        "type": "message",
        "webhookEventId": event_id,
        "replyToken": f"reply-{event_id}",
        "source": {"type": "user", "userId": "U" + "0" * 32},
        "message": {"type": "text", "id": "1", "text": text},
    }


def _body(*events: dict) -> bytes:
    return json.dumps({"destination": "x", "events": list(events)}).encode()


def _sign(body: bytes, secret: str = SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def _post(path: str, body: bytes, signature: str | bytes | None, **headers: str | bytes):
    if signature is not None:
        headers["X-Line-Signature"] = signature
    with TestClient(app) as client:
        return client.post(path, content=body, headers=headers)


@pytest.fixture
def line_settings(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    with patch("api.routes.line.settings") as mock_settings:
        mock_settings.line_channel_secret = SECRET
        mock_settings.line_tasks_queue = "line-events"
        yield mock_settings


@pytest.fixture
def enqueue():
    with patch("api.routes.line.enqueue_event", new_callable=AsyncMock) as mock_enqueue:
        yield mock_enqueue


@pytest.fixture
def handle():
    with patch("api.routes.line.handle_event", new_callable=AsyncMock) as mock_handle:
        yield mock_handle


# ── /webhook auth ───────────────────────────────────────────────────────────


def test_webhook_returns_503_when_unconfigured(line_settings, enqueue):
    line_settings.line_channel_secret = ""
    body = _body()
    assert _post("/api/line/webhook", body, _sign(body)).status_code == 503


@pytest.mark.parametrize("signature", [None, "wrong", "簽章".encode()])
def test_webhook_rejects_bad_signature(line_settings, enqueue, signature):
    resp = _post("/api/line/webhook", _body(_event("evt-1")), signature)
    assert resp.status_code == 401
    enqueue.assert_not_called()


def test_webhook_rejects_signature_for_a_different_body(line_settings, enqueue):
    resp = _post("/api/line/webhook", _body(_event("evt-1")), _sign(_body(_event("evt-2"))))
    assert resp.status_code == 401
    enqueue.assert_not_called()


# ── /webhook enqueue ────────────────────────────────────────────────────────


def test_webhook_verify_request_with_no_events(line_settings, enqueue):
    body = _body()
    resp = _post("/api/line/webhook", body, _sign(body))
    assert resp.status_code == 200
    enqueue.assert_not_called()


def test_webhook_enqueues_one_task_per_event(line_settings, enqueue):
    body = _body(_event("evt-1"), _event("evt-2"))
    signature = _sign(body)

    resp = _post("/api/line/webhook", body, signature)

    assert resp.status_code == 200
    target_url = "https://testserver/api/line/process"
    assert [call.args for call in enqueue.call_args_list] == [
        (body, signature, "evt-1", target_url),
        (body, signature, "evt-2", target_url),
    ]


def test_webhook_returns_500_when_enqueue_fails(line_settings, enqueue):
    enqueue.side_effect = RuntimeError("queue unavailable")
    body = _body(_event("evt-1"))
    assert _post("/api/line/webhook", body, _sign(body)).status_code == 500


def test_webhook_without_queue_handles_in_process(line_settings, enqueue, handle):
    line_settings.line_tasks_queue = ""
    body = _body(_event("evt-1"))

    resp = _post("/api/line/webhook", body, _sign(body))

    assert resp.status_code == 200
    enqueue.assert_not_called()
    handle.assert_called_once_with(_event("evt-1"))


def test_webhook_without_queue_on_cloud_run_is_refused(line_settings, enqueue, handle, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "navi-backend")
    line_settings.line_tasks_queue = ""
    body = _body(_event("evt-1"))

    resp = _post("/api/line/webhook", body, _sign(body))

    assert resp.status_code == 503
    handle.assert_not_called()


# ── /process ────────────────────────────────────────────────────────────────


def test_process_rejects_bad_signature(line_settings, handle):
    body = _body(_event("evt-1"))
    resp = _post("/api/line/process", body, "wrong", **{"X-Line-Event-Id": "evt-1"})
    assert resp.status_code == 401
    handle.assert_not_called()


def test_process_handles_only_the_named_event(line_settings, handle):
    body = _body(_event("evt-1", "第一題"), _event("evt-2", "第二題"))

    resp = _post("/api/line/process", body, _sign(body), **{"X-Line-Event-Id": "evt-2"})

    assert resp.status_code == 200
    handle.assert_awaited_once_with(_event("evt-2", "第二題"))


def test_process_ignores_unknown_event_id(line_settings, handle):
    body = _body(_event("evt-1"))
    resp = _post("/api/line/process", body, _sign(body), **{"X-Line-Event-Id": "evt-9"})
    assert resp.status_code == 200
    handle.assert_not_called()
