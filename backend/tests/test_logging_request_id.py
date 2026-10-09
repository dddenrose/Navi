"""Regression: log records from child loggers must format with the root LOG_FORMAT.

main.py 的 formatter 用到 ``%(request_id)s``。補值的 filter 若掛在 root *logger* 上，
子 logger propagate 上來的 record 不會經過它，formatter 會丟
``ValueError: Formatting field not found in record: 'request_id'``，線上每筆
services.* 的 log 都變成 ``--- Logging error ---`` traceback。
"""

import io
import logging
import uuid

import main


def _fake_root() -> tuple[logging.Logger, io.StringIO]:
    """A standalone logger tree with one handler using the production format."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(main.LOG_FORMAT))
    root = logging.getLogger(f"fake_root_{uuid.uuid4().hex}")
    root.propagate = False
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return root, stream


def test_child_logger_record_without_request_id_formats_with_dash():
    root, stream = _fake_root()
    main._install_request_id_filter(root)

    root.getChild("services.line.client").info("[LINE dry-run] POST %s", "/message/reply")

    out = stream.getvalue()
    assert "Logging error" not in out
    assert "[-]: [LINE dry-run] POST /message/reply" in out


def test_explicit_request_id_extra_still_wins():
    root, stream = _fake_root()
    main._install_request_id_filter(root)

    root.getChild("api.routes.chat").info("done", extra={"request_id": "abc123"})

    assert "[abc123]: done" in stream.getvalue()


def test_install_is_idempotent():
    root, _ = _fake_root()
    main._install_request_id_filter(root)
    main._install_request_id_filter(root)

    (handler,) = root.handlers
    assert sum(isinstance(f, main._RequestIdFilter) for f in handler.filters) == 1


def test_production_root_handlers_carry_the_filter():
    """每個已掛在真正 root 上、使用 LOG_FORMAT 的 handler 都要有這個 filter。"""
    for handler in logging.getLogger().handlers:
        fmt = getattr(handler.formatter, "_fmt", "") or ""
        if "request_id" in fmt:
            assert any(isinstance(f, main._RequestIdFilter) for f in handler.filters)
