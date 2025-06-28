from logging import INFO, basicConfig, getLogger
from typing import Any

from rich.logging import RichHandler

from .utils import Timer


class Logger:
    def __init__(self):
        basicConfig(
            format="%(message)s",
            datefmt="[%d-%m %X]",
            level=INFO,
            handlers=[RichHandler()],
        )
        self.logger = getLogger("rich")

    def info(self, log: str) -> None:
        self.logger.info(log)

    def error(self, err: Exception) -> None:
        self.logger.error(f"Error: {err}")

    def received(self, msg: Any) -> Timer:
        self.logger.info(
            f"[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{msg.from_user.username}: {msg.from_user.first_name} -> {msg.text}"
        )
        return Timer()

    def sent(self, msg: Any, timer: Timer) -> None:
        self.logger.info(
            f"[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{msg.from_user.username}: {msg.from_user.first_name} <- {timer.done()}"
        )
