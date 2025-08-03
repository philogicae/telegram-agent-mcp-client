# pylint: disable=arguments-differ
from typing import Any, Awaitable, Callable

from telebot.async_telebot import AsyncTeleBot
from telebot.types import Document, Message

from ..abstract import Bot


class TelegramBot(Bot):
    bot: AsyncTeleBot
    edit_cache: dict[int, list[str]] = {}

    def __init__(
        self,
        telegram_id: str,
        delay: float | None = None,
        group_msg_trigger: str | None = None,
        waiting: str | None = None,
    ):
        """Must call initialize() and start() after"""
        super().__init__(delay, group_msg_trigger, waiting)
        self.bot = AsyncTeleBot(
            token=telegram_id,
            parse_mode="MARKDOWN",
            disable_web_page_preview=True,
        )

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

        @self.bot.message_handler(
            func=lambda m: m.chat.type == "private"
            or (m.reply_to_message and m.reply_to_message.from_user.id == me.id)
            or m.text.startswith(self.group_msg_trigger),
            content_types=["document"],
        )  # type: ignore
        async def _handle_file(document: Document) -> None:
            handler = kwargs.get("document")
            if handler:
                await handler(document)

    async def start(self) -> None:
        await self.bot.infinity_polling(skip_pending=True, timeout=300)

    async def send(
        self, message_or_chat_id: Message | int | str, text: str | None = None
    ) -> Message:
        msg: Message = await self._exec(
            self.bot.send_message,
            (
                message_or_chat_id.chat.id
                if isinstance(message_or_chat_id, Message)
                else message_or_chat_id
            ),
            text or self.waiting,
        )
        if not text:
            self.edit_cache[msg.id] = [str(msg.text)]
        return msg

    async def reply(self, to_message: Message, text: str | None = None) -> Message:
        msg: Message = await self._exec(
            self.bot.reply_to, to_message, text or self.waiting
        )
        if not text:
            self.edit_cache[msg.id] = [str(msg.text)]
        return msg

    async def edit(
        self, message: Message, text: str, replace: bool = False, final: bool = False
    ) -> Message | bool:
        edited = text
        if not replace:
            if final:
                edited = (
                    "\n".join(self.edit_cache[message.id][:-1]) + f"\n\n{text}"
                ).strip()
            else:
                if text not in "✅❌":  # Tool call
                    self.edit_cache[message.id][-1] = text
                else:  # Tool result
                    self.edit_cache[message.id][-1] = (
                        f"{text}{self.edit_cache[message.id][-1][1:-3]}"
                    )
                    self.edit_cache[message.id].append(self.waiting)
                edited = "\n".join(self.edit_cache[message.id])
        msg: Message | bool = await self._exec(
            self.bot.edit_message_text, edited, message.chat.id, message.id
        )
        if (replace or final) and message.id in self.edit_cache:
            del self.edit_cache[message.id]
        return msg

    async def pin(self, message: Message) -> bool:
        success: bool = await self._exec(
            self.bot.pin_chat_message, message.chat.id, message.id, True
        )
        return success

    async def unpin(self, message: Message) -> bool:
        success: bool = await self._exec(
            self.bot.unpin_chat_message, message.chat.id, message.id
        )
        return success

    async def delete(self, message: Message) -> bool:
        success: bool = await self._exec(
            self.bot.delete_message, message.chat.id, message.id
        )
        return success
