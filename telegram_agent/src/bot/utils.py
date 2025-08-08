from time import time

from telebot.types import InlineKeyboardMarkup, Message
from telebot.util import quick_markup


class Timer:
    def __init__(self) -> None:
        self.start = time()

    def done(self) -> str:
        return f"{time() - self.start:.2f}s"


def odd_found(text: str, char: str) -> bool:
    return char in text and text.count(char) % 2 != 0


def escape_single_char(text: str, chars: list[str]) -> str:
    for char in chars:
        if odd_found(text, char):
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if odd_found(line, char):
                    c = line.rfind(char)
                    if c != -1:
                        lines[i] = f"{line[:c]}\\{char}{line[c + 1 :]}"
            text = "\n".join(lines)
    return text


def fixed_markdown(text: str) -> str:
    replacements = {
        "\n* ": "\n- ",
        "**": "*",
        "*`": "`",
        "`*": "`",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    escaped = ["*", "~"]
    return escape_single_char(text, escaped).strip()


def unpack_user(msg: Message) -> tuple[str, str]:
    if msg.from_user:
        return (
            msg.from_user.username or str(msg.from_user.id),
            msg.from_user.first_name,
        )
    return "?", "Unknown"


def progress_bar(current: int | float, total: int | float, size: int = 15) -> str:
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
