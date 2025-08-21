from telebot.types import InlineKeyboardMarkup, Message
from telebot.util import quick_markup
from telegramify_markdown import markdownify


def unpack_user(msg: Message) -> tuple[str, str]:
    if msg.from_user:
        return (
            msg.from_user.username or str(msg.from_user.id),
            msg.from_user.first_name,
        )
    return "?", "Unknown"


def fixed(text: str) -> str:
    return markdownify(text, normalize_whitespace=True)


def logify(agent: str | None = "Logs", content: list[str] | str = "") -> str:
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


def progress_bar(current: int | float, total: int | float, size: int = 15) -> str:
    if total < 1:
        total = 1
    ratio = current / total
    scaled_percent = int(size * ratio)
    progress = "▓" * scaled_percent + "░" * (size - scaled_percent)
    percent = f"{100 * ratio:.1f}%".rjust(5, " ")
    return f"{progress} {percent}"


def reply_markup(index: int, total: int) -> InlineKeyboardMarkup:
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
