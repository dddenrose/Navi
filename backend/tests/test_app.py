"""Smoke / integration tests for the FastAPI app (no external services)."""

from fastapi.testclient import TestClient

from main import app


def test_health_endpoint():
    """GET /health 應回傳 200 與 ok 狀態，並附上 X-Request-ID 標頭。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert resp.headers.get("x-request-id"), "middleware 應注入 X-Request-ID"


def test_root_endpoint_includes_request_id():
    """GET / 應回傳歡迎訊息並帶上 X-Request-ID。"""
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "Navi" in body["message"]
        rid = resp.headers.get("x-request-id")
        assert rid and len(rid) >= 8


def test_cors_preflight_allows_dev_origin():
    """允許清單內的 Origin 應通過 CORS preflight。"""
    with TestClient(app) as client:
        resp = client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type, authorization",
            },
        )
        # Starlette CORSMiddleware 對允許 origin 回 200，對未允許的則不附 ACAO
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_disallows_unknown_origin():
    """不在允許清單的 Origin 不應拿到 Access-Control-Allow-Origin。"""
    with TestClient(app) as client:
        resp = client.options(
            "/api/chat",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
