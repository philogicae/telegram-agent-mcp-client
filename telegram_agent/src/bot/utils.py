"""Utility functions for Telegram bot."""

import re
from typing import Any

from telebot.types import InlineKeyboardMarkup, Message
from telebot.util import quick_markup
from unidecode import unidecode


def unpack_user(msg: Message) -> tuple[str, str]:
    """Extract username and display name from a message."""
    if msg.from_user:
        return (
            msg.from_user.username or str(msg.from_user.id),
            msg.from_user.first_name,
        )
    return "?", "Unknown"


def fixed_telegram(_: Any, text: str) -> str:
    """Convert markdown text to Telegram HTML format (supports rich messages)."""
    text = text.replace("&", "&amp;")

    def _code_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = m.group(2).strip()
        if lang:
            return f'<pre><code class="language-{lang}">\n{code}\n</code></pre>'
        return f"<pre>\n{code}\n</pre>"

    text = re.sub(r"```(\w+)?\n?(.*?)```", _code_block, text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"~(.+?)~", r"<s>\1</s>", text)

    # Divider: ---
    text = re.sub(r"(?m)^(-{3,}|\*{3,}|_{3,})\s*$", r"<hr>", text)

    # Heading: ### text -> <h3>text</h3>
    def _heading(m: re.Match) -> str:
        level = len(m.group(1))
        return f"<h{level}>{m.group(2).strip()}</h{level}>"

    text = re.sub(r"(?m)^(#{1,6})\s+(.+)$", _heading, text)

    # Pipe tables: | ... | -> <table><tr><td>...</td></tr></table>
    def _table(m: re.Match) -> str:
        rows_html = []
        for raw in m.group(0).strip().split("\n"):
            line = raw.strip()
            if not line.startswith("|"):
                continue
            cells = line.strip("|").split("|")
            if all(set(c.strip()) <= set(" -:|") for c in cells):
                continue
            tag = "th" if not rows_html else "td"
            row = "".join(f"<{tag}>{c.strip()}</{tag}>" for c in cells)
            rows_html.append(f"<tr>{row}</tr>")
        return f"<table>\n{chr(10).join(rows_html)}\n</table>" if rows_html else ""

    text = re.sub(r"(?m)^\|.+\|\s*$(\n\|.+\|\s*$)*", _table, text)

    # Unordered list: - or * items
    def _ulist(m: re.Match) -> str:
        items = "".join(
            f"<li>{re.sub(r'^[\-\*]\s+', '', line).strip()}</li>"
            for line in m.group(0).split("\n")
            if line.strip()
        )
        return f"<ul>{items}</ul>"

    text = re.sub(r"(?m)^[\-\*]\s.*(\n[\-\*]\s.*)*", _ulist, text)

    # Ordered list: 1. items
    def _olist(m: re.Match) -> str:
        items = "".join(
            f"<li>{re.sub(r'^\d+\.\s+', '', line).strip()}</li>"
            for line in m.group(0).split("\n")
            if line.strip()
        )
        return f"<ol>{items}</ol>"

    text = re.sub(r"(?m)^\d+\.\s.*(\n\d+\.\s.*)*", _olist, text)

    # Blockquote
    text = re.sub(r"(?m)^>\s?(.*)$", r"<blockquote>\1</blockquote>", text)

    result, in_tag = [], False
    for char in text:
        if char == "<":
            in_tag = True
            result.append(char)
        elif char == ">":
            in_tag = False
            result.append(char)
        elif in_tag:
            result.append(char)
        elif char in "<>":
            result.append(f"&#{ord(char)};")
        else:
            result.append(char)
    result_str = "".join(result)
    return re.sub(r"\n{3,}", "\n\n", result_str.strip())


def logify_telegram(
    _: Any, agent: str | None = "Logs", content: list[str] | str = ""
) -> str:
    """Format log content for Telegram display."""
    logs = [content] if content and isinstance(content, str) else content
    if not logs:
        return ""
    label = agent.replace(" ", "-") if agent else "Logs"
    inner = "\n".join(logs)
    return f'<pre><code class="language-{label}">{inner}\n</code></pre>'


def progress_bar(current: float, total: float, size: int = 15) -> str:
    """Create a text-based progress bar."""
    total = max(total, 1)
    ratio = current / total
    scaled_percent = int(size * ratio)
    progress = "▓" * scaled_percent + "░" * (size - scaled_percent)
    percent = f"{100 * ratio:.1f}%".rjust(5, " ")
    return f"{progress} {percent}"


def reply_markup(index: int, total: int) -> InlineKeyboardMarkup:
    """Create pagination reply markup."""
    return quick_markup(
        {
            "⏮️": {"callback_data": "first"},
            "◀️": {"callback_data": "prev"},
            f"{index + 1}/{total}": {"callback_data": "none"},
            "▶️": {"callback_data": "next"},
            "⏭️": {"callback_data": "last"},
        },
        row_width=5,
    )


def str_size(size: int) -> str:
    """Format file size in human-readable format."""
    return (
        f"{size / 1024 / 1024:.2f}MB"
        if size > 1024 * 1024
        else f"{size / 1024:.2f}KB"
        if size > 1024
        else f"{size}B"
    )


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage."""
    filename = unidecode(filename)
    splitted = filename.rsplit(".", maxsplit=1)
    try:
        return (
            "".join(
                char if char.isalnum() or char in "-_" else "_" for char in splitted[0]
            )
            + "."
            + splitted[-1]
        ).lower()
    except Exception:
        return ""
