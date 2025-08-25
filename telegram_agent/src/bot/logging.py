from telebot.types import Message

from ..utils import Timer
from .abstract import Logger
from .utils import unpack_user


class TelegramLogger(Logger):
    instance: str = "TELEGRAM"

    def received(self, msg: Message) -> Timer:
        source = self.instance + ": " if self.instance else ""
        user, name = unpack_user(msg)
        self.logger.info(
            f"{source}[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{user}: {name} -> {msg.text}"
        )
        return super().received(msg)

    def sent(self, msg: Message, timer: Timer) -> None:
        source = self.instance + ": " if self.instance else ""
        user, name = unpack_user(msg)
        self.logger.info(
            f"{source}[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{user}: {name} <- {timer.done()}"
        )
