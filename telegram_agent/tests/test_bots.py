"""Tests for ``telegram_agent/src/bot/bots.py`` and bot logging."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from telegram_agent.src.bot import bots as bots_mod
from telegram_agent.src.bot.logging import TelegramLogger
from telegram_agent.tests.fakes import make_message


class FakeAgenticBot:
    last: dict[str, Any] = {}

    def __init__(
        self,
        telegram_id: str,
        dev: bool = False,
        managers: dict[str, type] | None = None,
        persist: bool = False,
        **kwargs: Any,
    ) -> None:
        FakeAgenticBot.last = {
            "telegram_id": telegram_id,
            "dev": dev,
            "managers": managers,
            "persist": persist,
        }
        self.handlers: dict[str, Any] = {}
        self.bot = object()

    def __enter__(self) -> FakeAgenticBot:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    async def run(self, **handlers: Any) -> None:
        self.handlers = handlers
        FakeAgenticBot.last["handlers"] = handlers


def patched_gather(calls: list[Any]):
    async def fake_gather(*aws: Any, **kwargs: Any) -> None:
        # Awaits the bot run (so handler wiring is observable), closes the rest.
        for extra in aws[1:]:
            extra.close()
        calls.append(aws)
        await aws[0]

    return fake_gather


class TestRunTelegramBot:
    async def test_prod_token_required(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            await bots_mod.run_telegram_bot()

    async def test_dev_token_required(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN_DEV", raising=False)
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN_DEV"):
            await bots_mod.run_telegram_bot(dev=True)

    async def test_wires_managers_and_handlers(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
        monkeypatch.setenv("TRANSMISSION_URL", "http://t")
        monkeypatch.setenv("RAG_URL", "http://rag")  # legacy var must be inert
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr(bots_mod, "AgenticTelegramBot", FakeAgenticBot)
        monkeypatch.setattr(bots_mod, "start_relay", lambda instance: None)
        closes: list[Any] = []
        monkeypatch.setattr(bots_mod, "gather", patched_gather(closes))

        await bots_mod.run_telegram_bot(dev=False, persist=True)

        assert FakeAgenticBot.last["telegram_id"] == "123:ABC"
        assert FakeAgenticBot.last["persist"] is True
        assert set(FakeAgenticBot.last["managers"]) == {"download_torrent"}
        assert set(FakeAgenticBot.last["handlers"]) == {"chat", "voice", "image"}
        assert closes  # gather got the bot run + nothing else

    async def test_dev_uses_dev_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "prod")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_DEV", "dev")
        monkeypatch.delenv("TRANSMISSION_URL", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr(bots_mod, "AgenticTelegramBot", FakeAgenticBot)
        monkeypatch.setattr(bots_mod, "start_relay", lambda instance: None)
        monkeypatch.setattr(bots_mod, "gather", patched_gather([]))
        await bots_mod.run_telegram_bot(dev=True)
        assert FakeAgenticBot.last["telegram_id"] == "dev"
        assert FakeAgenticBot.last["managers"] == {}
        assert set(FakeAgenticBot.last["handlers"]) == {"chat"}

    async def test_relay_app_is_served_too(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
        monkeypatch.delenv("TRANSMISSION_URL", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr(bots_mod, "AgenticTelegramBot", FakeAgenticBot)
        monkeypatch.setattr(bots_mod, "start_relay", lambda instance: "app")
        serve = AsyncMock()
        monkeypatch.setattr(bots_mod, "serve", serve)
        closes: list[Any] = []
        monkeypatch.setattr(bots_mod, "gather", patched_gather(closes))
        await bots_mod.run_telegram_bot()
        assert serve.await_count == 0  # coroutine closed by the gather stub
        assert len(closes[0]) == 2  # bot.run + serve(relay)


class TestTelegramLogger:
    def test_received_and_sent_lines(self, caplog):
        logger = TelegramLogger()
        msg = make_message("hello", chat_id=5)
        timer = logger.received(msg)
        logger.sent(msg, timer)
        assert "[5]" in caplog.text
        assert "@456: Tester" in caplog.text

    def test_group_title_used(self, caplog):
        logger = TelegramLogger()
        msg = make_message(
            "hello",
            chat_id=5,
            chat_type="group",
            **{"chat": {"id": 5, "type": "group", "title": "Team"}},
        )
        logger.received(msg)
        assert "Team" in caplog.text
