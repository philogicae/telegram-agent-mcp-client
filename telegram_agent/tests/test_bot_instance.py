"""Tests for ``telegram_agent/src/bot/instances/telegram.py``."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from telebot.asyncio_helper import ApiException

from telegram_agent.src.bot.instances.telegram import (
    TelegramBot,
    _is_private_or_reply,
    _PollingExceptionHandler,
    _render_logify,
)
from telegram_agent.tests.fakes import make_message


def plain_logify(agent: str | None, content: list[str]) -> str:
    return f"{agent}:" + "|".join(content)


def make_bot(**kwargs: Any) -> TelegramBot:
    bot = TelegramBot("123:ABC", **kwargs)
    bot.core.send_message = AsyncMock(return_value=make_message("sent"))
    bot.core.reply_to = AsyncMock(return_value=make_message("replied"))
    bot.core.edit_message_text = AsyncMock(return_value=make_message("edited"))
    return bot


class TestPrivateOrReply:
    def test_private_chat_always(self):
        assert _is_private_or_reply(make_message(), 42)

    def test_group_reply_to_bot(self):
        reply = {
            "message_id": 2,
            "from": {"id": 42, "is_bot": True, "first_name": "Bot"},
            "chat": {"id": 5, "type": "group"},
            "date": 0,
            "text": "hi",
        }
        msg = make_message(chat_id=5, chat_type="group", reply_to_message=reply)
        assert _is_private_or_reply(msg, 42)
        assert not _is_private_or_reply(msg, 99)

    def test_group_without_reply(self):
        assert not _is_private_or_reply(make_message(chat_type="group"), 42)


class TestRenderLogify:
    def test_panel_filters_waiting_and_appends_model_text(self):
        out = _render_logify(
            plain_logify, "waiting", "A", ["line", "waiting"], model_text="panel"
        )
        assert out == "A:line\npanel"

    def test_tool_block_folded_into_block(self):
        out = _render_logify(plain_logify, "waiting", "A", ["line"], tool_block="tools")
        assert out == "A:line|tools"

    def test_no_panel_keeps_waiting(self):
        assert _render_logify(plain_logify, "waiting", "A", ["waiting"]) == "A:waiting"


class TestPollingExceptionHandler:
    async def test_api_exception_keeps_polling(self):
        exc = ApiException(
            "Bad Gateway", "getUpdates", {"error_code": 502, "description": "blip"}
        )
        assert await _PollingExceptionHandler().handle(exc) is True

    async def test_other_exception_keeps_polling(self):
        assert await _PollingExceptionHandler().handle(ValueError("x")) is True

    async def test_episode_warns_once_then_recovers(self, caplog):
        handler = _PollingExceptionHandler()
        exc = ApiException(
            "Bad Gateway", "getUpdates", {"error_code": 502, "description": "blip"}
        )
        with caplog.at_level(
            "INFO", logger="telegram_agent.src.bot.instances.telegram"
        ):
            for _ in range(7):
                await handler.handle(exc)
            handler.recovered()
            await handler.handle(exc)  # a new episode warns again
        own = [
            r
            for r in caplog.records
            if r.name == "telegram_agent.src.bot.instances.telegram"
        ]
        warnings = [r for r in own if r.levelname == "WARNING"]
        infos = [r for r in own if r.levelname == "INFO"]
        assert len(warnings) == 2
        assert len(infos) == 1
        assert "after 7 hiccup" in infos[0].getMessage()

    async def test_recovered_without_episode_is_silent(self, caplog):
        with caplog.at_level("INFO"):
            _PollingExceptionHandler().recovered()
        assert not [
            r
            for r in caplog.records
            if r.name == "telegram_agent.src.bot.instances.telegram"
        ]


class TestDynamicLength:
    def test_picks_smaller_bucket_when_remainder_aligns(self):
        bot = make_bot()
        assert bot.max_msg_length == 1000
        assert bot._dynamic_length("x" * 1600) == 1000
        assert bot._dynamic_length("x" * 1000) == 1500

    def test_custom_max_length(self):
        bot = make_bot(max_msg_length=100)
        bot.extra_msg_length = 350
        assert bot.max_msg_length == 100
        assert bot._dynamic_length("x" * 460) == 100


class TestSendReply:
    async def test_send_short_formats_text(self):
        bot = make_bot()
        msg = await bot.send(1, "**bold**")
        assert msg.text == "sent"
        assert "<b>bold</b>" in bot.core.send_message.await_args.args[1]

    async def test_send_without_text_uses_waiting_and_caches(self):
        bot = make_bot()
        msg = await bot.send(1)
        assert bot.core.send_message.await_args.args[1] == bot.waiting
        assert bot.edit_cache[msg.id]["content"] == [bot.waiting]

    async def test_send_long_uses_pagination(self):
        bot = make_bot()
        bot.paginated = AsyncMock(return_value=make_message("paged"))
        msg = await bot.send(1, "x" * 1600)
        assert msg.text == "paged"
        bot.paginated.assert_awaited_once()

    async def test_reply_long_uses_pagination(self):
        bot = make_bot()
        bot.paginated = AsyncMock(return_value=make_message("paged"))
        msg = await bot.reply(make_message(), "x" * 1600)
        assert msg.text == "paged"

    async def test_reply_short(self):
        bot = make_bot()
        msg = await bot.reply(make_message(), "hi")
        assert msg.text == "replied"
        assert bot.core.reply_to.await_count == 1

    async def test_reply_without_text_caches(self):
        bot = make_bot()
        msg = await bot.reply(make_message())
        assert bot.edit_cache[msg.id]["current"] == 0


class TestEdit:
    def setup_edit(self) -> tuple[TelegramBot, Any]:
        bot = make_bot()
        message = make_message("orig")
        bot.edit_cache[message.id] = {"current": 0, "content": [bot.waiting]}
        return bot, message

    async def test_without_cache_returns_false(self):
        bot = make_bot()
        assert await bot.edit(make_message(), "text") is False

    async def test_normal_edit_updates_content(self):
        bot, message = self.setup_edit()
        result = await bot.edit(message, "new")
        assert result is not False
        assert bot.edit_cache[message.id]["content"] == ["new", bot.waiting]

    async def test_model_text_slot(self):
        bot, message = self.setup_edit()
        await bot.edit(message, "panel", model_text=True)
        assert bot.edit_cache[message.id]["model_text"] == "panel"

    async def test_tool_block_slot(self):
        bot, message = self.setup_edit()
        await bot.edit(message, "🛠️ Tool...", tool_block=True)
        assert bot.edit_cache[message.id]["tool_block"] == "🛠️ Tool..."

    async def test_unchanged_render_skips_api_call(self):
        bot, message = self.setup_edit()
        bot.edit_cache[message.id]["model_text"] = "panel"
        assert await bot.edit(message, "panel", model_text=True) is False
        assert bot.core.edit_message_text.await_count == 0

    async def test_replace_bypasses_cache(self):
        bot = make_bot()
        message = make_message("orig")
        assert await bot.edit(message, "text", replace=True) is not False
        assert message.id not in bot.edit_cache

    async def test_final_sends_rich_message(self):
        bot, message = self.setup_edit()
        rich = make_message("rich")
        bot._send_rich = AsyncMock(return_value=rich)
        bot.delete = AsyncMock(return_value=True)
        result = await bot.edit(message, "done", final=True)
        assert result is rich
        bot.delete.assert_awaited_once_with(message)
        assert message.id not in bot.edit_cache

    async def test_final_keeps_completed_tool_logs(self):
        """The final reply shows what ran, minus live status lines."""
        bot = make_bot()
        message = make_message("orig")
        bot.edit_cache[message.id] = {
            "current": 0,
            "content": ["🔁 Transfer", bot.waiting],
            "tool_block": "🛠️ Search...\n✅ Search: 1.20s\n❌ List Tasks: 0.30s",
        }
        bot._send_rich = AsyncMock(return_value=make_message("rich"))
        bot.delete = AsyncMock(return_value=True)
        await bot.edit(message, "done", final=True)
        html = bot._send_rich.await_args.args[1]
        assert "🔁 Transfer" in html
        assert "✅ Search: 1.20s" in html
        assert "❌ List Tasks: 0.30s" in html
        assert "🛠️" not in html
        assert "done" in html

    async def test_final_without_completed_tools_is_text_only(self):
        bot, message = self.setup_edit()
        bot._send_rich = AsyncMock(return_value=make_message("rich"))
        bot.delete = AsyncMock(return_value=True)
        await bot.edit(message, "done", final=True)
        html = bot._send_rich.await_args.args[1]
        assert "done" in html
        assert "<pre>" not in html

    async def test_long_edit_uses_pagination(self):
        bot, message = self.setup_edit()
        bot.paginated = AsyncMock(return_value=make_message("paged"))
        await bot.edit(message, "x" * 1600)
        bot.paginated.assert_awaited_once()

    async def test_edit_failure_is_swallowed(self):
        bot, message = self.setup_edit()
        bot.core.edit_message_text = AsyncMock(side_effect=RuntimeError("nope"))
        assert await bot.edit(message, "new") is False


class TestPaginated:
    async def test_send_page_caches(self):
        bot = make_bot()
        method = AsyncMock(return_value=make_message("paged"))
        msg = await bot.paginated(method, 1, "hello")
        assert bot.edit_cache[msg.id]["pages"] == ["hello"]
        assert bot.edit_cache[msg.id]["current"] == 0

    async def test_edit_tuple_ref(self):
        bot = make_bot()
        method = AsyncMock(return_value=make_message("paged"))
        await bot.paginated(method, (1, 2), "hello")
        assert method.await_args.args[1:] == (1, 2)

    async def test_existing_cache_without_content_gets_it(self):
        bot = make_bot()
        method = AsyncMock(return_value=make_message("paged"))
        msg = await bot.paginated(method, 1, "hi")
        bot.edit_cache[msg.id].pop("content")
        await bot.paginated(method, 1, "hi")
        assert bot.edit_cache[msg.id]["content"] == ["hi"]


class TestChangePage:
    def setup_cache(self) -> tuple[TelegramBot, Any, Any]:
        bot = make_bot()
        message = make_message("page")
        bot.edit_cache[message.id] = {
            "current": 0,
            "content": ["a b c"],
            "pages": ["a", "b", "c"],
        }
        return bot, message, bot.core.edit_message_text

    async def test_next_and_last_and_wrap(self):
        bot, message, edit = self.setup_cache()
        await bot.change_page(message, "next")
        assert bot.edit_cache[message.id]["current"] == 1
        await bot.change_page(message, "last")
        assert bot.edit_cache[message.id]["current"] == 2
        await bot.change_page(message, "next")
        assert bot.edit_cache[message.id]["current"] == 0
        assert edit.await_count == 3

    async def test_prev_wraps_backwards(self):
        bot, message, _ = self.setup_cache()
        await bot.change_page(message, "prev")
        assert bot.edit_cache[message.id]["current"] == 2

    async def test_unknown_message_or_action_is_noop(self):
        bot, message, edit = self.setup_cache()
        await bot.change_page(make_message("other", message_id=999), "next")
        await bot.change_page(message, "bogus")
        assert edit.await_count == 0


class TestPinUnpinDelete:
    async def test_success_paths(self):
        bot = make_bot()
        bot.core.pin_chat_message = AsyncMock(return_value=True)
        bot.core.unpin_chat_message = AsyncMock(return_value=True)
        bot.core.delete_message = AsyncMock(return_value=True)
        message = make_message("m")
        assert await bot.pin(message) is True
        assert await bot.unpin(message) is True
        assert await bot.delete(message) is True

    async def test_failures_are_suppressed(self):
        bot = make_bot(delay=0.001, retries=1)
        bot.core.pin_chat_message = AsyncMock(side_effect=RuntimeError("no"))
        bot.core.unpin_chat_message = AsyncMock(side_effect=RuntimeError("no"))
        bot.core.delete_message = AsyncMock(side_effect=RuntimeError("no"))
        message = make_message("m")
        assert await bot.pin(message) is False
        assert await bot.unpin(message) is False
        assert await bot.delete(message) is False


class TestSendRich:
    def message_json(self) -> dict[str, Any]:
        return {
            "message_id": 1,
            "chat": {"id": 1, "type": "private"},
            "date": 0,
            "text": "rich",
        }

    async def test_first_attempt_success(self):
        bot = make_bot()
        bot._exec = AsyncMock(return_value=self.message_json())
        msg = await bot._send_rich(1, "<b>hi</b>")
        assert msg.text == "rich"
        assert bot._exec.await_count == 1

    async def test_retries_without_images_then_succeeds(self):
        bot = make_bot()
        bot._exec = AsyncMock(side_effect=[RuntimeError("media"), self.message_json()])
        html = '<img src="http://x/i.png"/>caption'
        await bot._send_rich(1, html)
        assert bot._exec.await_count == 2
        assert "img" not in bot._exec.await_args.args[2]["rich_message"]["html"]

    async def test_falls_back_to_plain_text(self):
        bot = make_bot()
        bot._exec = AsyncMock(side_effect=RuntimeError("always"))
        bot.paginated = AsyncMock(return_value=make_message("plain"))
        msg = await bot._send_rich(1, "<b>hi</b>")
        assert msg.text == "plain"
        bot.paginated.assert_awaited_once()

    async def test_plain_html_fails_once_then_falls_back(self):
        bot = make_bot()
        bot._exec = AsyncMock(side_effect=RuntimeError("always"))
        bot.paginated = AsyncMock(return_value=make_message("plain"))
        await bot._send_rich(1, "text only")
        assert bot._exec.await_count == 1


class TestInitializeAndStart:
    async def test_initialize_requires_chat_handler(self):
        bot = make_bot()
        bot.core.set_my_commands = AsyncMock()
        bot.core.get_me = AsyncMock(return_value=SimpleNamespace(id=42))
        with pytest.raises(ValueError, match="Chat handler is required"):
            await bot.initialize()

    async def test_initialize_registers_all_handlers(self):
        bot = make_bot()
        bot.core.set_my_commands = AsyncMock()
        bot.core.get_me = AsyncMock(return_value=SimpleNamespace(id=42))
        await bot.initialize(
            chat=AsyncMock(),
            document=AsyncMock(),
            voice=AsyncMock(),
            image=AsyncMock(),
        )
        assert bot.id == "42"

    async def test_start_polls_with_timeout(self):
        bot = make_bot()
        bot.core.infinity_polling = AsyncMock()
        await bot.start()
        bot.core.infinity_polling.assert_awaited_once_with(
            skip_pending=True, timeout=30
        )

    async def test_start_reports_recovery_after_successful_poll(self):
        bot = make_bot()
        poll = AsyncMock(return_value=[])
        bot.core.get_updates = poll
        recovered = Mock()
        bot._exception_handler.recovered = recovered

        async def poll_once(**kwargs: Any) -> None:
            await bot.core.get_updates()

        bot.core.infinity_polling = AsyncMock(side_effect=poll_once)
        await bot.start()
        recovered.assert_called_once()
        poll.assert_awaited_once()
