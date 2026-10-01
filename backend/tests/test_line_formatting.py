"""Tests for LINE text formatting — Markdown stripping and message splitting."""

from services.line.formatting import (
    MAX_MESSAGES,
    TRUNCATION_NOTICE,
    format_for_line,
    split_messages,
    to_plain_text,
    utf16_len,
)

# ── to_plain_text ───────────────────────────────────────────────────────────


def test_strips_bold_and_italic():
    text = "這是 **重點** 與 __另一個重點__ 和 *斜體*"
    assert to_plain_text(text) == "這是 重點 與 另一個重點 和 斜體"


def test_strips_headings_and_blockquotes():
    assert to_plain_text("## 技術面\n> 引用內容\n正文") == "技術面\n引用內容\n正文"


def test_strips_code_fences_and_inline_code():
    assert to_plain_text("```python\nprint(1)\n```\n用 `RSI` 判斷") == "print(1)\n用 RSI 判斷"


def test_links_become_label_and_url():
    assert to_plain_text("[鉅亨網](https://cnyes.com/a)") == "鉅亨網 https://cnyes.com/a"
    assert to_plain_text("[https://x.io](https://x.io)") == "https://x.io"


def test_dash_and_star_bullets_become_dots():
    assert to_plain_text("- 第一點\n* 第二點\n  - 子項") == "• 第一點\n• 第二點\n  • 子項"


def test_tables_are_flattened():
    table = "| 指標 | 數值 |\n| --- | :---: |\n| RSI | 72 |"
    assert to_plain_text(table) == "指標 | 數值\nRSI | 72"


def test_horizontal_rules_removed_and_blank_lines_collapsed():
    assert to_plain_text("上段\n\n---\n\n\n\n下段") == "上段\n\n下段"


def test_existing_answer_style_is_untouched():
    answer = "📌 現況摘要：現價 1,050 元\n  • 技術支撐區：MA20\n⚠️ 風險提醒：-5% 以內"
    assert to_plain_text(answer) == answer


def test_arithmetic_asterisks_are_kept():
    assert to_plain_text("成本 = 100 * 1.001425 * 1000") == "成本 = 100 * 1.001425 * 1000"


# ── utf16_len / split_messages ──────────────────────────────────────────────


def test_utf16_len_counts_astral_emoji_as_two():
    assert utf16_len("台積電") == 3
    assert utf16_len("📈") == 2


def test_short_text_is_one_message():
    assert split_messages("短訊息") == ["短訊息"]


def test_blank_text_yields_no_messages():
    assert split_messages("") == []
    assert format_for_line("  \n\n ") == []


def test_splits_on_paragraph_boundaries():
    text = "\n\n".join(["甲" * 40, "乙" * 40, "丙" * 40])
    assert split_messages(text, limit=90) == ["甲" * 40 + "\n\n" + "乙" * 40, "丙" * 40]


def test_long_paragraph_falls_back_to_lines_then_hard_split():
    text = "甲" * 30 + "\n" + "乙" * 130
    messages = split_messages(text, limit=50)
    assert messages == ["甲" * 30, "乙" * 50, "乙" * 50, "乙" * 30]


def test_limit_is_measured_in_utf16_units():
    messages = split_messages("📈" * 60, limit=50)
    assert all(utf16_len(message) <= 50 for message in messages)
    assert "".join(messages) == "📈" * 60


def test_caps_message_count_with_truncation_notice():
    text = "\n\n".join(str(i) * 80 for i in range(9))
    messages = split_messages(text, limit=100, max_messages=3)
    assert len(messages) == 3
    assert messages[-1].endswith(TRUNCATION_NOTICE)
    assert all(utf16_len(message) <= 100 for message in messages)


def test_format_for_line_strips_markdown_and_respects_limits():
    answer = "\n\n".join(f"## 第 {i} 段\n**重點** " + "字" * 3000 for i in range(12))
    messages = format_for_line(answer)
    assert len(messages) == MAX_MESSAGES
    assert all(utf16_len(message) <= 5000 for message in messages)
    assert "**" not in "".join(messages) and "##" not in "".join(messages)
