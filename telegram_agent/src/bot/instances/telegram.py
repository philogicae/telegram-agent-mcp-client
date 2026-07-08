"""Telegram bot instance implementation."""

from collections.abc import Awaitable, Callable
from contextlib import suppress
from logging import getLogger
from typing import Any, ClassVar

import aiohttp
from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, LinkPreviewOptions, Message
from telebot.util import smart_split

from ..abstract import Bot
from ..utils import (
    fixed_telegram,
    logify_telegram,
    reply_markup,
    strip_html_tags,
    strip_rich_images,
)

logger = getLogger(__name__)

msg_params: dict[str, Any] = {
    "link_preview_options": LinkPreviewOptions(is_disabled=True)
}


class TelegramBot(Bot):
    """Telegram bot implementation using AsyncTeleBot."""

    core: AsyncTeleBot
    fixed: Callable[..., str] = fixed_telegram
    logify: Callable[..., str] = logify_telegram
    max_msg_length: int = 1000
    extra_msg_length: int = 500
    pagination_action: ClassVar[list[str]] = ["first", "prev", "next", "last"]

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
        """Initialize the Telegram bot. Must call initialize() and start() after."""
        super().__init__(delay, group_msg_trigger, waiting, retries)
        if max_msg_length:
            self.max_msg_length = max_msg_length
        self.core = AsyncTeleBot(token=telegram_id, parse_mode="HTML")
        self.edit_cache: dict[int, Any] = {}

    async def _rich_request(self, method: str, params: dict) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.core.token}/{method}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(url, json=params) as resp,
        ):
            resp.raise_for_status()
            result: dict[str, Any] = await resp.json()
            if not result.get("ok"):
                raise RuntimeError(f"Telegram API error: {result}")
            return result["result"]

    async def _send_rich(self, chat_id: int, content_html: str) -> Message:
        """
        Send a rich HTML message, degrading gracefully on failure.

        Telegram rejects the whole message if it cannot fetch an embedded
        image (RICH_MESSAGE_PHOTO_NO_MEDIA_FOUND). Since the placeholder
        message is already deleted by then, a raw failure would leave the
        user with no answer at all. So we retry without images, then fall
        back to plain text, guaranteeing a response is always delivered.
        """
        stripped = strip_rich_images(content_html)
        attempts = [content_html] + ([stripped] if stripped != content_html else [])
        for html in attempts:
            try:
                result = await self._exec(
                    self._rich_request,
                    "sendRichMessage",
                    {"chat_id": chat_id, "rich_message": {"html": html}},
                    retries=0,
                )
                return Message.de_json(result)
            except Exception as exc:
                logger.warning("sendRichMessage attempt failed: %s", exc)
                continue
        return await self.paginated(
            self.core.send_message, chat_id, strip_html_tags(content_html)
        )

    async def initialize(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        """Set up message handlers for the bot."""
        await self.core.set_my_commands([])
        me = await self.core.get_me()

        # Handlers
        handle_chat = kwargs.get("chat")
        if not handle_chat:
            raise ValueError("Chat handler is required")
        handle_document = kwargs.get("document")
        handle_voice = kwargs.get("voice")
        handle_image = kwargs.get("image")

        def _is_private_or_reply(m: Message) -> bool:
            return m.chat.type == "private" or (
                m.reply_to_message is not None
                and m.reply_to_message.from_user is not None
                and m.reply_to_message.from_user.id == me.id
            )

        @self.core.message_handler(
            func=lambda m: (
                _is_private_or_reply(m) or m.text.startswith(self.group_msg_trigger)
            ),
            content_types=["text"],
        )
        async def _handle_message(message: Message) -> None:
            """
            Handle message.

            Private: Every message.
            Group: If it's a reply to the bot or starts with group_msg_trigger.
            """
            text = str(message.text).strip()
            if text.startswith(self.group_msg_trigger):
                message.text = text[1:].strip()
            await handle_chat(message)

        @self.core.callback_query_handler(
            func=lambda call: call.data in self.pagination_action
        )
        async def _handle_page(call: CallbackQuery) -> None:
            if isinstance(call.message, Message):
                await self.change_page(call.message, call.data)

        if handle_document:

            @self.core.message_handler(
                func=_is_private_or_reply,
                content_types=["document"],
            )
            async def _handle_file(message: Message) -> None:
                await handle_document(message)

        if handle_voice:

            @self.core.message_handler(
                func=_is_private_or_reply,
                content_types=["voice"],
            )
            async def _handle_voice(message: Message) -> None:
                await handle_voice(message)

        if handle_image:

            @self.core.message_handler(
                func=_is_private_or_reply,
                content_types=["photo"],
            )
            async def _handle_photo(message: Message) -> None:
                await handle_image(message)

    async def start(self) -> None:
        """Start the bot's polling loop."""
        await self.core.infinity_polling(skip_pending=True, timeout=300)

    async def send(
        self,
        message_or_chat_id: Message | int | str,
        text: str | None = None,
    ) -> Message:
        """Send a message to a chat."""
        ref: int = (
            message_or_chat_id.chat.id
            if isinstance(message_or_chat_id, Message)
            else int(message_or_chat_id)
        )
        if text and len(text) > self._dynamic_length(text):
            return await self.paginated(self.core.send_message, ref, self.fixed(text))
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
        """Reply to a specific message."""
        if text and len(text) > self._dynamic_length(text):
            return await self.paginated(
                self.core.reply_to, to_message, self.fixed(text)
            )
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
        """Edit an existing message."""
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
                content[-1] = text  # Tool result edit / Tool call init or logs
                if not content[-1].endswith("..."):
                    content.append(self.waiting)
                edited = self.logify(agent, content)
        msg: Message | bool = False
        if edited != orig:
            content_html = self.fixed(edited)
            if final:
                await self.delete(message)
                msg = await self._send_rich(message.chat.id, content_html)
            elif len(content_html) > self._dynamic_length(content_html):
                msg = await self.paginated(
                    self.core.edit_message_text,
                    (message.chat.id, message.id),
                    content_html,
                    cache.get("current"),
                )
            else:
                msg = await self._exec(
                    self.core.edit_message_text,
                    content_html,
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
        """Send or edit a paginated message."""
        max_length = self._dynamic_length(text)
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
        """Change the page of a paginated message."""
        cache = self.edit_cache.get(message.id)
        if cache and "pages" in cache and action in self.pagination_action:
            move = -1 if action == "prev" else 1
            new_index = 0
            if action in ["prev", "next"]:
                new_index = ((len(cache["pages"]) + cache["current"]) + move) % len(
                    cache["pages"]
                )
            if action == "last":
                new_index = len(cache["pages"]) - 1
            if cache["current"] != new_index:
                cache["current"] = new_index
                await self._exec(
                    self.core.edit_message_text,
                    cache["pages"][new_index],
                    message.chat.id,
                    message.id,
                    reply_markup=reply_markup(new_index, len(cache["pages"])),
                    **msg_params,
                )

    async def pin(self, message: Message) -> bool:
        """Pin a message in a chat."""
        success: bool = False
        with suppress(Exception):
            success = await self._exec(
                self.core.pin_chat_message,
                message.chat.id,
                message.id,
                disable_notification=True,
            )
        return success

    async def unpin(self, message: Message) -> bool:
        """Unpin a message in a chat."""
        success: bool = False
        with suppress(Exception):
            success = await self._exec(
                self.core.unpin_chat_message, message.chat.id, message.id
            )
        return success

    async def delete(self, message: Message) -> bool:
        """Delete a message from a chat."""
        success: bool = False
        with suppress(Exception):
            success = await self._exec(
                self.core.delete_message, message.chat.id, message.id
            )
        return success
