# pylint: disable=arguments-differ
from typing import Any, Awaitable, Callable

from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, LinkPreviewOptions, Message
from telebot.util import smart_split

from ..abstract import Bot
from ..utils import fixed_telegram, logify_telegram, reply_markup

msg_params: dict[str, Any] = {
    "link_preview_options": LinkPreviewOptions(is_disabled=True)
}


class TelegramBot(Bot):
    core: AsyncTeleBot
    fixed: Callable[..., str] = fixed_telegram
    logify: Callable[..., str] = logify_telegram
    max_msg_length: int = 1000
    extra_msg_length: int = 500
    pagination_action: list[str] = ["first", "prev", "next", "last"]

    def _dynamic_length(self, text: str) -> tuple[int, int]:
        include_quote = text.split("||\n", maxsplit=1)
        if len(include_quote) > 1:
            return self._dynamic_length(include_quote[1])[0], len(include_quote[0]) + 3
        return (
            (
                self.max_msg_length
                if len(text) % self.max_msg_length
                > len(text) % (self.max_msg_length + self.extra_msg_length)
                else self.max_msg_length + self.extra_msg_length
            ),
            0,
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
        self.core = AsyncTeleBot(token=telegram_id, parse_mode="MarkdownV2")
        self.edit_cache: dict[int, Any] = {}

    async def initialize(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        await self.core.set_my_commands([])
        me = await self.core.get_me()

        # Handlers
        handle_chat = kwargs.get("chat")
        if not handle_chat:
            raise ValueError("Chat handler is required")
        handle_document = kwargs.get("document")

        @self.core.message_handler(
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
            await handle_chat(message)

        @self.core.callback_query_handler(
            func=lambda call: call.data in self.pagination_action
        )  # type: ignore
        async def _handle_page(call: CallbackQuery) -> None:
            if isinstance(call.message, Message):
                await self.change_page(call.message, call.data)

        if handle_document:

            @self.core.message_handler(
                func=lambda m: m.chat.type == "private"
                or (m.reply_to_message and m.reply_to_message.from_user.id == me.id),
                content_types=["document"],
            )  # type: ignore
            async def _handle_file(message: Message) -> None:
                await handle_document(message)

    async def start(self) -> None:
        await self.core.infinity_polling(skip_pending=True, timeout=300)

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
        if text and len(text) > self._dynamic_length(text)[0]:
            paginated_msg: Message = await self.paginated(
                self.core.send_message, ref, self.fixed(text)
            )
            return paginated_msg
        msg: Message = await self._exec(
            self.core.send_message,
            ref,
            self.fixed(text or self.waiting),
            **msg_params,
        )
        if not text:
            self.edit_cache[msg.id] = {"current": 0, "content": [self.waiting]}
        return msg

    async def reply(
        self,
        to_message: Message,
        text: str | None = None,
    ) -> Message:
        if text and len(text) > self._dynamic_length(text)[0]:
            paginated_msg: Message = await self.paginated(
                self.core.reply_to, to_message, self.fixed(text)
            )
            return paginated_msg
        msg: Message = await self._exec(
            self.core.reply_to,
            to_message,
            self.fixed(text or self.waiting),
            **msg_params,
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
            orig = self.logify(agent, content)
            if final:
                edited = (self.logify(agent, content[:-1]) + f"\n{text}").strip()
            else:
                if "🛠️" in content[-1] and text in "✅❌":  # Tool result edit
                    content[-1] = f"{text}{content[-1][1:-3]}"
                else:  # Tool call init or logs
                    content[-1] = text
                if not content[-1].endswith("..."):
                    content.append(self.waiting)
                edited = self.logify(agent, content)
        msg: Message | bool = False
        if edited != orig:
            if edited and len(edited) > self._dynamic_length(edited)[0]:  # Paginated
                msg = await self.paginated(
                    self.core.edit_message_text,
                    (message.chat.id, message.id),
                    self.fixed(edited),
                    cache.get("current"),
                )
            else:  # Single message
                msg = await self._exec(
                    self.core.edit_message_text,
                    self.fixed(edited),
                    message.chat.id,
                    message.id,
                    **msg_params,
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
        max_length, quote_length = self._dynamic_length(text)
        pages: list[str] = []
        if quote_length:
            pages = smart_split(text[quote_length:], max_length)
            pages[0] = text[:quote_length] + pages[0]
        else:
            pages = smart_split(text, max_length)
        msg: Any = None
        if isinstance(ref, tuple):  # Edit
            msg = await self._exec(
                method,
                pages[page],
                ref[0],
                ref[1],
                reply_markup=reply_markup(page, len(pages)),
                **msg_params,
            )
        else:  # Send/Reply
            msg = await self._exec(
                method,
                ref,
                pages[page],
                reply_markup=reply_markup(page, len(pages)),
                **msg_params,
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
                    self.core.edit_message_text,
                    self.fixed(cache["pages"][new_index]),
                    message.chat.id,
                    message.id,
                    reply_markup=reply_markup(new_index, len(cache["pages"])),
                    **msg_params,
                )

    async def pin(self, message: Message) -> bool:
        success: bool = False
        try:
            success = await self._exec(
                self.core.pin_chat_message, message.chat.id, message.id, True
            )
        except Exception:
            pass
        return success

    async def unpin(self, message: Message) -> bool:
        success: bool = False
        try:
            success = await self._exec(
                self.core.unpin_chat_message, message.chat.id, message.id
            )
        except Exception:
            pass
        return success

    async def delete(self, message: Message) -> bool:
        success: bool = False
        try:
            success = await self._exec(
                self.core.delete_message, message.chat.id, message.id
            )
        except Exception:
            pass
        return success
