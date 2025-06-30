from telebot.types import Message

from .abstract import Logger
from .utils import Timer


class TelegramLogger(Logger):
    instance: str = "TELEGRAM"

    def unpack_user(self, msg: Message) -> tuple[str, str]:
        if msg.from_user:
            return (
                msg.from_user.username or str(msg.from_user.id),
                msg.from_user.first_name,
            )
        return "?", "Unknown"

    def received(self, msg: Message) -> Timer:
        source = self.instance + ": " if self.instance else ""
        user, name = self.unpack_user(msg)
        self.logger.info(
            f"{source}[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{user}: {name} -> {msg.text}"
        )
        return super().received(msg)

    def sent(self, msg: Message, timer: Timer) -> None:
        source = self.instance + ": " if self.instance else ""
        user, name = self.unpack_user(msg)
        self.logger.info(
            f"{source}[{msg.chat.id}] {msg.chat.title or 'Private'}\n@{user}: {name} <- {timer.done()}"
        )
