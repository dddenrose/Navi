"""Tests for screener Stage 3 prompts & number-hallucination validator."""

from __future__ import annotations

from services.screener.prompts import (
    StockInterpretation,
    build_interpreter_system_prompt,
    build_interpreter_user_prompt,
    format_allowed_numbers,
    validate_narrative,
)


# ── Dynamic system prompt ──────────────────────────────────────────────────


def test_value_system_prompt_contains_value_trap_playbook():
    sp = build_interpreter_system_prompt("value")
    assert "<value_trap_playbook>" in sp
    assert "Dividend trap" in sp
    assert "1-3 年" in sp  # value horizon
    # 不應包含 momentum 限制段
    assert "<value_trap_note>" not in sp


def test_momentum_system_prompt_drops_value_trap_playbook():
    sp = build_interpreter_system_prompt("momentum")
    assert "<value_trap_playbook>" not in sp
    assert "Dividend trap" not in sp
    assert "1-3 個月" in sp  # momentum horizon
    assert "value_trap_check 一律填" in sp


# ── User prompt ─────────────────────────────────────────────────────────────


def test_user_prompt_embeds_snapshot_and_allowed_numbers():
    text = build_interpreter_user_prompt(
        "value",
        "<stock><ticker>2330.TW</ticker></stock>",
        format_allowed_numbers({"pe": "22.50", "roe_3y_avg": "15.20%"}),
    )
    assert "2330.TW" in text
    assert "<allowed_numbers>" in text
    assert "22.50" in text
    assert "15.20%" in text


def test_format_allowed_numbers_empty():
    assert format_allowed_numbers({}) == "<allowed_numbers/>"


# ── Schema ──────────────────────────────────────────────────────────────────


def test_stock_interpretation_defaults():
    si = StockInterpretation(narrative="x")
    # 預設 not_applicable：「沒有檢查」不得冒充「已檢查無虞」(no_concern)
    assert si.value_trap_check == "not_applicable"
    assert si.value_trap_reason == ""
    assert si.key_context == []
    assert si.warnings == []


def test_stock_interpretation_accepts_not_applicable():
    si = StockInterpretation(narrative="x", value_trap_check="not_applicable")
    assert si.value_trap_check == "not_applicable"


# ── validate_narrative ──────────────────────────────────────────────────────


def test_validate_narrative_allows_whitelisted_pct():
    text = "ROE 約 15.2%，殖利率 3.5%。"
    allowed = {"roe_3y_avg": 0.152, "dividend_yield": 0.035}
    assert validate_narrative(text, allowed) == []


def test_validate_narrative_allows_whitelisted_multiple():
    text = "本益比 22.5 倍，淨值比 2.1 倍。"
    allowed = {"pe": 22.5, "pb": 2.1}
    assert validate_narrative(text, allowed) == []


def test_validate_narrative_flags_hallucinated_pct():
    text = "ROE 高達 28.0%，遠勝同業。"
    allowed = {"roe_3y_avg": 0.152}  # 實際只有 15.2%
    violations = validate_narrative(text, allowed)
    assert any("28" in v for v in violations)


def test_validate_narrative_flags_hallucinated_multiple():
    text = "本益比僅 8.0 倍。"
    allowed = {"pe": 22.5}
    violations = validate_narrative(text, allowed)
    assert any("8.0" in v for v in violations)


def test_validate_narrative_tolerance_pct():
    # 寫 15.0%，實際 15.2%，預設 ±0.5pp 容忍 → 通過
    text = "ROE 約 15.0%。"
    allowed = {"roe_3y_avg": 0.152}
    assert validate_narrative(text, allowed) == []


def test_validate_narrative_ignores_unitless_integers():
    # 「3 年」「4 季」這類純整數沒有單位（年/季不在偵測單位內），不應被誤判
    text = "近 3 年 ROE 平均 15.2%，連續 4 季 EPS 為正。"
    allowed = {"roe_3y_avg": 0.152}
    assert validate_narrative(text, allowed) == []


def test_validate_narrative_empty_text():
    assert validate_narrative("", {"pe": 22.5}) == []


def test_validate_narrative_price_relative_tolerance():
    # 價格用相對誤差 5%
    text = "目標價 105.0 元。"
    allowed = {"fair_value_mid": 100.0}  # 差 5%，邊界內
    assert validate_narrative(text, allowed) == []

    text2 = "目標價 130.0 元。"
    violations = validate_narrative(text2, allowed)
    assert any("130" in v for v in violations)


# ── Grounding（質性接地）────────────────────────────────────────────────────


def test_system_prompt_forbids_ungrounded_business_facts():
    for profile in ("value", "momentum"):
        sp = build_interpreter_system_prompt(profile)
        assert "質性事實接地" in sp
        assert "只能來自輸入資料" in sp


def test_user_prompt_reminds_grounding():
    up = build_interpreter_user_prompt("value", "<stock/>", "<allowed_numbers/>")
    assert "輸入沒有的不要寫" in up
