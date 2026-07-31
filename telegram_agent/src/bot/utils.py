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


def _code_block(m: re.Match) -> str:
    lang = m.group(1) or ""
    code = m.group(2).strip()
    if lang:
        return f'<pre><code class="language-{lang}">\n{code}\n</code></pre>'
    return f"<pre>\n{code}\n</pre>"


def _image(m: re.Match) -> str:
    url, title = m.group(2), m.group(3)
    if url.startswith(("http://", "https://")):
        if title:
            return (
                f'<figure><img src="{url}"/><figcaption>{title}</figcaption></figure>'
            )
        return f'<img src="{url}"/>'
    return ""


def _heading(m: re.Match) -> str:
    level = len(m.group(1))
    return f"<h{level}>{m.group(2).strip()}</h{level}>"


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


def _ulist(m: re.Match) -> str:
    items = ""
    for raw_line in m.group(0).split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        task = re.match(r"^[\-\*\+]\s+\[([ xX])\]\s+(.*)", line)
        if task:
            checked = task.group(1).lower() == "x"
            items += f'<li><input type="checkbox"{" checked" if checked else ""}/>{task.group(2)}</li>'
        else:
            content = re.sub(r"^[\-\*\+]\s+", "", line)
            items += f"<li>{content}</li>"
    return f"<ul>{items}</ul>"


def _olist(m: re.Match) -> str:
    items = "".join(
        f"<li>{re.sub(r'^\d+\.\s+', '', line).strip()}</li>"
        for line in m.group(0).split("\n")
        if line.strip()
    )
    return f"<ol>{items}</ol>"


def _convert_list(m: re.Match) -> str:
    tag = m.group(1)
    inner = m.group(2)
    items = re.findall(r"<li>(.*?)</li>", inner, flags=re.DOTALL)
    if tag == "ol":
        return "\n".join(f"{i}. {item.strip()}" for i, item in enumerate(items, 1))
    return "\n".join(f"• {item.strip()}" for item in items)


def _convert_table(m: re.Match) -> str:
    inner = m.group(1)
    rows = re.findall(r"<tr>(.*?)</tr>", inner, flags=re.DOTALL)
    lines = []
    for row in rows:
        cells_th = re.findall(r"<th>(.*?)</th>", row, flags=re.DOTALL)
        cells_td = re.findall(r"<td>(.*?)</td>", row, flags=re.DOTALL)
        cells = cells_th or cells_td
        if cells:
            lines.append(" | ".join(c.strip() for c in cells))
    return "\n".join(lines)


_LIST_PATTERN = re.compile(r"<(ol|ul)>((?:(?!<(?:ol|ul)>).)*?)</\1>", re.DOTALL)


def fixed_telegram(_: Any, text: str, classic: bool = True) -> str:
    """Convert markdown text to Telegram HTML format.

    When classic=True (default), rich-only tags (<ol>, <ul>, <table>, <h1>-<h6>,
    <mark>, <figure>, <img>, <input>, <hr>) are converted to classic-safe
    equivalents for send_message/edit_message_text. When classic=False, rich
    tags are preserved for sendRichMessage.
    """
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;)", "&amp;", text)
    text = re.sub(r"```(\w+)?\n?(.*?)```", _code_block, text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', _image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"==(.+?)==", r"<mark>\1</mark>", text)
    text = re.sub(r"(?m)^(-{3,}|\*{3,}|_{3,})\s*$", r"<hr>", text)
    text = re.sub(r"(?m)^(#{1,6})\s+(.+)$", _heading, text)
    text = re.sub(r"(?m)^\|.+\|\s*$(\n\|.+\|\s*$)*", _table, text)
    text = re.sub(r"(?m)^[\-\*\+]\s.*(\n[\-\*\+]\s.*)*", _ulist, text)
    text = re.sub(r"(?m)^\d+\.\s.*(\n\d+\.\s.*)*", _olist, text)

    text = re.sub(r"(?m)^>\s?(.*)$", r"<blockquote>\1</blockquote>", text)

    # Escape < and > that aren't part of HTML tags or entities.
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "<":
            tag = re.match(r"</?[a-zA-Z][^>]*>", text[i:])
            if tag:
                result.append(tag.group(0))
                i += len(tag.group(0))
            else:
                result.append("&lt;")
                i += 1
        elif text[i] == ">":
            result.append("&gt;")
            i += 1
        else:
            result.append(text[i])
            i += 1
    html = "".join(result).strip()
    if classic:
        html = _sanitize_classic(html)
    return re.sub(r"\n{3,}", "\n\n", html)


def _sanitize_classic(html: str) -> str:
    """Convert rich-only HTML tags to classic-safe equivalents."""
    html = re.sub(r"<input[^>]*/?>", "", html)
    html = re.sub(r"</?figure>", "", html)
    html = re.sub(r"<figcaption>(.*?)</figcaption>", r"\1", html, flags=re.DOTALL)
    html = re.sub(r"<img[^>]*/?>", "", html)
    html = re.sub(r"<h([1-6])>(.*?)</h\1>", r"<b>\2</b>", html, flags=re.DOTALL)
    html = re.sub(r"<mark>(.*?)</mark>", r"<u>\1</u>", html, flags=re.DOTALL)
    html = re.sub(r"<hr>", "\n———\n", html)

    # Convert lists to plain text, innermost first for nesting.
    while True:
        new_html = _LIST_PATTERN.sub(_convert_list, html)
        if new_html == html:
            break
        html = new_html

    html = re.sub(r"<table>(.*?)</table>", _convert_table, html, flags=re.DOTALL)
    return html


def strip_rich_images(html: str) -> str:
    """
    Remove media tags and unwrap <figure>/<figcaption> from rich HTML.

    Used as a fallback when Telegram's sendRichMessage rejects a message
    because it could not fetch one of the embedded media URLs
    (RICH_MESSAGE_PHOTO_NO_MEDIA_FOUND). Captions are kept as plain text.
    """
    html = re.sub(r"<(?:img|video|audio|tg-collage|tg-slideshow)[^>]*?/?>", "", html)
    html = re.sub(r"<figcaption>(.*?)</figcaption>", r"\1", html, flags=re.DOTALL)
    html = re.sub(r"</?figure>", "", html)
    return re.sub(r"\n{3,}", "\n\n", html).strip()


def strip_html_tags(html: str) -> str:
    """
    Reduce rich HTML to tag-free text (last-resort Telegram fallback).

    Entities (&amp;, &lt;, ...) are kept escaped so the result stays valid
    under Telegram's HTML parse mode used by send_message.
    """
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def logify_telegram(
    _: Any, agent: str | None = "Logs", content: list[str] | str = ""
) -> str:
    """Format log content for Telegram display."""
    logs = [content] if content and isinstance(content, str) else content
    if not logs:
        return ""
    label = agent.replace(" ", "-") if agent else "Logs"
    inner = (
        "\n".join(logs).replace("\x00", "").replace("<", "&lt;").replace(">", "&gt;")
    )
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
