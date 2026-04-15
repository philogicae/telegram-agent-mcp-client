"""Utility functions for Telegram bot."""

from re import sub
from typing import Any

from telebot.formatting import mcite
from telebot.types import InlineKeyboardMarkup, Message
from telebot.util import quick_markup
from telegramify_markdown import markdownify
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
    """Fix Telegram markdown formatting."""
    include_quote = text.split("||\n", maxsplit=1)
    if len(include_quote) > 1:
        return include_quote[0] + "||\n" + fixed_telegram(_, include_quote[1])
    fixed = markdownify(html_to_markdown(text))
    fixed = sub(r"\n{2,}", "\n\n", fixed)  # Remove extra newlines
    fixed = sub(r"\n[\t ]+", "\n", fixed)  # Remove leading tabs and spaces
    return fixed.strip().replace("\\\\", "\\")  # Remove double backslashes


def logify_telegram(
    _: Any, agent: str | None = "Logs", content: list[str] | str = ""
) -> str:
    """Format log content for Telegram display."""
    logs = [content] if content and isinstance(content, str) else content
    return (
        (
            f"```{agent.replace(' ', '-') if agent else 'Logs'}\n"
            + "\n".join(logs)
            + "\n```"
        )
        if logs
        else ""
    )


def quotify_telegram(_: Any, text: str) -> str:
    """Format text as a Telegram quote."""
    return mcite(text, escape=True, expandable=True)


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


def transform_urls(html_text: str) -> str:
    """Transform HTML anchor tags to Markdown links."""
    # <a href="URL">TEXT</a> -> [TEXT](URL)
    pattern = r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>'
    replacement = r"[\2](\1)"
    return sub(pattern, replacement, html_text)


def transform_images(html_text: str) -> str:
    """Transform HTML img tags to Markdown image links."""
    # <img src="URL" ...> -> [](URL)
    pattern = r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]+)"[^>]*\/>'
    replacement = r"> [IMG: \2](\1)"
    return sub(pattern, replacement, html_text)


def transform_linked_images(html_text: str) -> str:
    """Transform HTML linked images to Markdown."""
    # <a ...><img src="URL" ...></a> -> [](URL)
    pattern = r'<a[^>]*>\s*<img[^>]*src="([^"]+)"[^>]*alt="([^"]+)"[^>]*\/>\s*<\/a>'
    replacement = r"> [IMG: \2](\1)"
    return sub(pattern, replacement, html_text)


def quote_report_id(html_text: str) -> str:
    """Quote report IDs in the text."""
    return html_text.replace("```\nReport", "```\n> Report")


def html_to_markdown(html_text: str) -> str:
    """Convert HTML text to Markdown format."""
    return quote_report_id(
        transform_urls(transform_images(transform_linked_images(html_text)))
    )
