from time import time

from telebot.types import Message


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
    return escape_single_char(text, ["*", "~"]).strip()


def unpack_user(msg: Message) -> tuple[str, str]:
    if msg.from_user:
        return (
            msg.from_user.username or str(msg.from_user.id),
            msg.from_user.first_name,
        )
    return "?", "Unknown"
