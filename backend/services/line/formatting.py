"""LINE 文字訊息格式化 — Markdown 轉純文字、依長度切段.

LINE 文字訊息不渲染 Markdown，且單則上限 5000 字（以 UTF-16 code unit 計，
emoji 算 2）、一次 reply / push 最多 5 則。
"""

import re

MESSAGE_LIMIT = 4500  # 低於 LINE 的 5000 上限，留餘裕
MAX_MESSAGES = 5
TRUNCATION_NOTICE = "\n\n…（內容過長已截斷，完整版請到 Navi 網頁查看）"

_FENCE_RE = re.compile(r"^[ \t]*```.*$\n?", re.MULTILINE)
_RULE_RE = re.compile(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$\n?", re.MULTILINE)
_TABLE_SEPARATOR_RE = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$\n?", re.MULTILINE
)
_TABLE_ROW_RE = re.compile(r"^[ \t]*\|(.+)\|[ \t]*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_QUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?", re.MULTILINE)
_BULLET_RE = re.compile(r"^([ \t]*)[-*][ \t]+", re.MULTILINE)
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\((https?://[^\s)]+)\)")
_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<![*\w])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![*\w])")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units — how LINE counts message characters."""
    return len(text.encode("utf-16-le")) // 2


def _link_to_text(match: re.Match) -> str:
    label, url = match.group(1).strip(), match.group(2)
    return url if not label or label == url else f"{label} {url}"


def _table_row_to_text(match: re.Match) -> str:
    cells = [cell.strip() for cell in match.group(1).split("|")]
    return " | ".join(cell for cell in cells if cell)


def to_plain_text(text: str) -> str:
    """Strip Markdown syntax that LINE would show as literal symbols."""
    text = text.replace("\r\n", "\n")
    text = _FENCE_RE.sub("", text)
    text = _TABLE_SEPARATOR_RE.sub("", text)
    text = _RULE_RE.sub("", text)
    text = _TABLE_ROW_RE.sub(_table_row_to_text, text)
    text = _HEADING_RE.sub("", text)
    text = _QUOTE_RE.sub("", text)
    text = _BULLET_RE.sub(r"\1• ", text)
    text = _LINK_RE.sub(_link_to_text, text)
    text = _BOLD_RE.sub(r"\2", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


def _hard_split(text: str, limit: int) -> list[str]:
    """Split by characters, never cutting a surrogate pair in half."""
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for char in text:
        char_len = 2 if ord(char) > 0xFFFF else 1
        if current and current_len + char_len > limit:
            pieces.append("".join(current))
            current, current_len = [], 0
        current.append(char)
        current_len += char_len
    if current:
        pieces.append("".join(current))
    return pieces


def _units(text: str, limit: int):
    """Yield (separator, unit) pieces no longer than ``limit``.

    優先在段落邊界切，其次行邊界，最後才硬切。
    """
    for para_index, para in enumerate(text.split("\n\n")):
        para_sep = "\n\n" if para_index else ""
        if utf16_len(para) <= limit:
            yield para_sep, para
            continue
        for line_index, line in enumerate(para.split("\n")):
            line_sep = "\n" if line_index else para_sep
            if utf16_len(line) <= limit:
                yield line_sep, line
                continue
            for piece_index, piece in enumerate(_hard_split(line, limit)):
                yield ("" if piece_index else line_sep), piece


def split_messages(
    text: str, limit: int = MESSAGE_LIMIT, max_messages: int = MAX_MESSAGES
) -> list[str]:
    """Split text into at most ``max_messages`` messages of at most ``limit`` units."""
    messages: list[str] = []
    current = ""
    for separator, unit in _units(text, limit):
        if current and utf16_len(current) + utf16_len(separator) + utf16_len(unit) <= limit:
            current += separator + unit
        else:
            if current:
                messages.append(current)
            current = unit
    if current:
        messages.append(current)
    messages = [message.strip() for message in messages if message.strip()]

    if len(messages) > max_messages:
        messages = messages[:max_messages]
        room = limit - utf16_len(TRUNCATION_NOTICE)
        last = messages[-1]
        if utf16_len(last) > room:
            last = _hard_split(last, room)[0].rstrip()
        messages[-1] = last + TRUNCATION_NOTICE
    return messages


def format_for_line(answer: str) -> list[str]:
    """Turn an agent answer into LINE-ready text messages (empty list if blank)."""
    return split_messages(to_plain_text(answer))
