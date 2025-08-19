# pylint: disable=arguments-differ
from typing import Any, Awaitable, Callable

from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, LinkPreviewOptions, Message
from telebot.util import smart_split

from ..abstract import Bot
from ..utils import fixed, logify, reply_markup

disable_web_page_preview = {
    "link_preview_options": LinkPreviewOptions(is_disabled=True)
}


class TelegramBot(Bot):
    bot: AsyncTeleBot
    max_msg_length: int = 1000
    extra_msg_length: int = 500
    pagination_action: list[str] = ["first", "prev", "next", "last"]

    def _dynamic_length(self, text: str) -> int:
        return (
            self.max_msg_length
            if len(text) % self.max_msg_length
            > len(text) % (self.max_msg_length + self.extra_msg_length)
            else self.max_msg_length + self.extra_msg_length
        )

    def __init__(
        self,
        telegram_id: str,
        delay: float | None = None,
        group_msg_trigger: str | None = None,
        waiting: str | None = None,
        retries: int | None = None,
        max_msg_length: int | None = None,
    ):
        """Must call initialize() and start() after"""
        super().__init__(delay, group_msg_trigger, waiting, retries)
        if max_msg_length:
            self.max_msg_length = max_msg_length
        self.bot = AsyncTeleBot(token=telegram_id, parse_mode="MarkdownV2")
        self.edit_cache: dict[int, Any] = {}

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

        @self.bot.callback_query_handler(
            func=lambda call: call.data in self.pagination_action
        )  # type: ignore
        async def _handle_page(call: CallbackQuery) -> None:
            if isinstance(call.message, Message):
                await self.change_page(call.message, call.data)

        @self.bot.message_handler(
            func=lambda m: m.chat.type == "private"
            or (m.reply_to_message and m.reply_to_message.from_user.id == me.id),
            content_types=["document"],
        )  # type: ignore
        async def _handle_file(message: Message) -> None:
            handler = kwargs.get("document")
            if handler:
                await handler(message)

    async def start(self) -> None:
        await self.bot.infinity_polling(skip_pending=True, timeout=300)

    async def send(
        self,
        message_or_chat_id: Message | int | str,
        text: str | None = None,
    ) -> Message:
        ref: Message | int | str = (
            message_or_chat_id.chat.id
            if isinstance(message_or_chat_id, Message)
            else message_or_chat_id
        )
        if text and len(text) > self._dynamic_length(text):
            paginated_msg: Message = await self.paginated(
                self.bot.send_message, ref, fixed(text)
            )
            return paginated_msg
        msg: Message = await self._exec(
            self.bot.send_message,
            ref,
            fixed(text or self.waiting),
            **disable_web_page_preview,
        )
        if not text:
            self.edit_cache[msg.id] = {"current": 0, "content": [self.waiting]}
        return msg

    async def reply(
        self,
        to_message: Message,
        text: str | None = None,
    ) -> Message:
        if text and len(text) > self._dynamic_length(text):
            paginated_msg: Message = await self.paginated(
                self.bot.reply_to, to_message, fixed(text)
            )
            return paginated_msg
        msg: Message = await self._exec(
            self.bot.reply_to,
            to_message,
            fixed(text or self.waiting),
            **disable_web_page_preview,
        )
        if not text:
            self.edit_cache[msg.id] = {"current": 0, "content": [self.waiting]}
        return msg

    async def edit(
        self,
        message: Message,
        text: str,
        replace: bool = False,
        final: bool = False,
        agent: str | None = None,
    ) -> Message | bool:
        if not replace and message.id not in self.edit_cache:
            return False
        orig, edited = "", text
        cache = self.edit_cache.get(message.id, {})
        if not replace:
            content = cache.get("content")
            if not content:
                return False
            orig = logify(agent, content)
            if final:
                edited = (logify(agent, content[:-1]) + f"\n{text}").strip()
            else:
                if "🛠️" in content[-1] and text in "✅❌":  # Tool result edit
                    content[-1] = f"{text}{content[-1][1:-3]}"
                else:  # Tool call init or logs
                    content[-1] = text
                if not content[-1].endswith("..."):
                    content.append(self.waiting)
                edited = logify(agent, content)
        msg: Message | bool = False
        if edited != orig:
            if edited and len(edited) > self._dynamic_length(edited):  # Paginated
                msg = await self.paginated(
                    self.bot.edit_message_text,
                    (message.chat.id, message.id),
                    fixed(edited),
                    cache.get("current"),
                )
            else:  # Single message
                msg = await self._exec(
                    self.bot.edit_message_text,
                    fixed(edited),
                    message.chat.id,
                    message.id,
                    **disable_web_page_preview,
                )
                if (replace or final) and message.id in self.edit_cache:
                    del self.edit_cache[message.id]
        return msg

    async def paginated(
        self,
        method: Callable[..., Awaitable[Any]],
        ref: Message | int | str | tuple[int, int],
        text: str,
        page: int = 0,
    ) -> Any:
        pages = smart_split(text, self._dynamic_length(text))
        msg: Any = None
        if isinstance(ref, tuple):  # Edit
            msg = await self._exec(
                method,
                pages[page],
                ref[0],
                ref[1],
                reply_markup=reply_markup(page, len(pages)),
                **disable_web_page_preview,
            )
        else:  # Send/Reply
            msg = await self._exec(
                method,
                ref,
                pages[page],
                reply_markup=reply_markup(page, len(pages)),
                **disable_web_page_preview,
            )
        cache = self.edit_cache.get(msg.id)
        if not cache:
            cache = {"current": page, "content": [text], "pages": pages}
            self.edit_cache[msg.id] = cache
        elif "content" not in cache:
            cache["content"] = [text]
        cache.update({"current": page, "pages": pages})
        return msg

    async def change_page(self, message: Message, action: str | None = None) -> None:
        cache = self.edit_cache.get(message.id)
        if cache and "pages" in cache and action in self.pagination_action:
            move = -1 if action == "prev" else 1
            new_index = 0
            if action in ["prev", "next"]:
                new_index = ((len(cache["pages"]) + cache["current"]) + move) % len(
                    cache["pages"]
                )
            if action in ["last"]:
                new_index = len(cache["pages"]) - 1
            if cache["current"] != new_index:
                cache["current"] = new_index
                await self._exec(
                    self.bot.edit_message_text,
                    fixed(cache["pages"][new_index]),
                    message.chat.id,
                    message.id,
                    reply_markup=reply_markup(new_index, len(cache["pages"])),
                    **disable_web_page_preview,
                )

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
