from time import sleep, time
from typing import Any, Awaitable, Callable

from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

from ..abstract import Bot


class TelegramBot(Bot):
    bot: AsyncTeleBot
    last_call: float = 0
    delay: float = 0.2
    group_msg_trigger: str = "!"
    waiting: str = "💭 I'm thinking..."
    edit_cache: dict[int, list[str]] = {}

    def __init__(
        self,
        telegram_id: str,
        delay: float | None = None,
        group_msg_trigger: str | None = None,
        waiting: str | None = None,
    ):
        """Must call initialize() and start() after"""
        self.bot = AsyncTeleBot(
            token=telegram_id,
            parse_mode="MARKDOWN",
            disable_web_page_preview=True,
        )
        if delay:
            self.delay = delay
        if group_msg_trigger:
            self.group_msg_trigger = group_msg_trigger
        if waiting:
            self.waiting = waiting

    async def initialize(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        await self.bot.set_my_commands([])
        me = await self.bot.get_me()

        @self.bot.message_handler(
            func=lambda m: m.chat.type == "private"
            or (m.reply_to_message and m.reply_to_message.from_user.id == me.id)
            or m.text.startswith(self.group_msg_trigger),
            content_types=["text"],
        )  # type: ignore
        async def _handle_message(message: Message) -> None:
            """Handle message:
            # Private
                - Every message
            # Group
                - If it's a reply to the bot
                - If it starts with group_msg_trigger
            """
            text = str(message.text).strip()
            if text.startswith(self.group_msg_trigger):
                message.text = text[1:].strip()
            handler = kwargs.get("chat")
            if handler:
                await handler(message)

    async def start(self) -> None:
        await self.bot.infinity_polling(skip_pending=True, timeout=300)

    def called(self) -> None:
        self.last_call = time()

    def is_free(self) -> bool:
        return self.last_call + self.delay < time()

    async def exec(
        self, method: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Message:
        while True:
            if self.is_free():
                try:
                    result: Message = await method(*args, **kwargs)
                    self.called()
                    return result
                except Exception:
                    pass
            else:
                sleep(self.delay)

    async def send(self, message: Message, text: str | None = None) -> Message:
        msg = await self.exec(
            self.bot.send_message, message.chat.id, text or self.waiting
        )
        if not text:
            self.edit_cache[msg.id] = [str(msg.text)]
        return msg

    async def reply(self, to_message: Message, text: str | None = None) -> Message:
        msg = await self.exec(self.bot.reply_to, to_message, text or self.waiting)
        if not text:
            self.edit_cache[msg.id] = [str(msg.text)]
        return msg

    async def edit(self, message: Message, text: str, replace: bool = False) -> Message:
        edited = text
        if replace:
            del self.edit_cache[message.id]
        else:
            if text != "✅":
                self.edit_cache[message.id].insert(-1, text)
            else:
                self.edit_cache[message.id][-2] = (
                    f"✅ {self.edit_cache[message.id][-2][2:-3]}"
                )
            edited = "\n".join(self.edit_cache[message.id])
        return await self.exec(
            self.bot.edit_message_text, edited, message.chat.id, message.id
        )

    async def final(
        self, message: Message, text: str, replace: bool = False
    ) -> Message:
        edited = text
        if not replace:
            edited = "\n".join(self.edit_cache[message.id][:-1]) + f"\n\n{text}"
        del self.edit_cache[message.id]
        return await self.exec(
            self.bot.edit_message_text, edited, message.chat.id, message.id
        )
