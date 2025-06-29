from typing import Any

from .abstract import Logger
from .utils import Timer


class TelegramLogger(Logger):
    def received(self, msg: Any) -> Timer:
        self.logger.info(
            f"[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{msg.from_user.username}: {msg.from_user.first_name} -> {msg.text}"
        )
        return super().received(msg)

    def sent(self, msg: Any, timer: Timer) -> None:
        self.logger.info(
            f"[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{msg.from_user.username}: {msg.from_user.first_name} <- {timer.done()}"
        )
