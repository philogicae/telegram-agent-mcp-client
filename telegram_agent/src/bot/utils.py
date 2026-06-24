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

    def _image(m: re.Match) -> str:
        url, title = m.group(2), m.group(3)
        if url.startswith(("http://", "https://")):
            if title:
                return f'<figure><img src="{url}"/><figcaption>{title}</figcaption></figure>'
            return f'<img src="{url}"/>'
        return ""

    text = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', _image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"==(.+?)==", r"<mark>\1</mark>", text)

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

    # Unordered list: -, *, or + items (including task lists)
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

    text = re.sub(r"(?m)^[\-\*\+]\s.*(\n[\-\*\+]\s.*)*", _ulist, text)

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

    # Escape < and > that aren't part of HTML tags or entities.
    # After markdown processing the text contains generated HTML tags
    # (e.g. <b>, <pre>, <a href="…">) alongside literal angle brackets
    # from user text. Only the latter must be escaped.
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
    return re.sub(r"\n{3,}", "\n\n", "".join(result).strip())


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
    inner = "\n".join(logs).replace("<", "&lt;").replace(">", "&gt;")
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
