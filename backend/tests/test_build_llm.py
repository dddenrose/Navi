"""_build_llm：模型、端點與 thinking 設定要跟 config 一致."""

from unittest.mock import patch

from config import Settings, settings
from services import agent_service
from services.screener import ai_evaluator


def _chat_kwargs(module, model_name: str | None = None) -> dict:
    with patch.object(module, "vertexai"), patch.object(module, "ChatVertexAI") as chat:
        module._build_llm(model_name)
    return chat.call_args.kwargs


def test_paid_model_uses_global_endpoint_with_capped_thinking():
    kwargs = _chat_kwargs(agent_service, settings.gemini_model_name)
    assert kwargs["model_name"] == settings.gemini_model_name
    assert kwargs["location"] == settings.gemini_location
    assert kwargs["thinking_budget"] == settings.gemini_thinking_budget


def test_free_model_has_no_thinking_cap():
    kwargs = _chat_kwargs(agent_service, settings.gemini_model_name_free)
    assert kwargs["model_name"] == settings.gemini_model_name_free
    assert kwargs["location"] == settings.gemini_location
    assert "thinking_budget" not in kwargs


def test_default_model_is_the_paid_one():
    assert _chat_kwargs(agent_service)["model_name"] == settings.gemini_model_name


def test_screener_llm_uses_global_endpoint():
    kwargs = _chat_kwargs(ai_evaluator)
    assert kwargs["model_name"] == settings.screener_llm_model
    assert kwargs["location"] == settings.gemini_location


def test_defaults_do_not_use_retired_gemini_2_x():
    # Gemini 2.5 全系列 2026-10-20 在 Vertex AI 退場，之後呼叫會 404
    defaults = Settings(_env_file=None)
    for name in (
        defaults.gemini_model_name,
        defaults.gemini_model_name_free,
        defaults.screener_llm_model,
    ):
        assert not name.startswith("gemini-2."), name
