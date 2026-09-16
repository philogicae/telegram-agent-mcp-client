"""Tests for ``telegram_agent/src/bot/abstract.py``."""

from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest

from telegram_agent.src.bot import abstract


class DummyLogger(abstract.Logger):
    instance = "DUMMY"
    level = 10  # DEBUG, so the delegation test can assert every level

    def received(self, msg: Any) -> Any:
        return super().received(msg)

    def sent(self, msg: Any, timer: Any) -> None:
        return super().sent(msg, timer)


class DummyBot(abstract.Bot):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.calls: list[Any] = []

    async def initialize(self, **kwargs: Any) -> None:
        self.calls.append(("initialize", kwargs))

    async def start(self) -> None:
        self.calls.append("start")

    async def send(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def reply(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def edit(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def pin(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def unpin(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        return None


class TestLogger:
    def test_delegates_to_python_logger(self, caplog):
        logger = DummyLogger()
        logger.info("info")
        logger.warning("warn")
        logger.warning("warning")
        logger.error("error")
        logger.debug("debug")
        assert all(
            text in caplog.text
            for text in ("info", "warn", "warning", "error", "debug")
        )

    def test_received_returns_timer(self):
        assert isinstance(DummyLogger().received(object()), abstract.Timer)


class TestContracts:
    def test_fixed_default_returns_text(self):
        assert abstract.fixed_default(None, "abc") == "abc"

    def test_logify_default_formats(self):
        assert abstract.logify_default(None, "A B", "line") == "A-B:\nline"
        assert abstract.logify_default(None, None, ["a", "b"]) == "Logs:\na\nb"


class TestBotThrottleAndExec:
    async def test_throttle_sleeps_for_remaining_gap(self, monkeypatch):
        bot = DummyBot(delay=0.5)
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(abstract, "sleep", fake_sleep)
        await bot._throttle()
        await bot._throttle()
        assert sleeps
        assert 0 < sleeps[0] <= 0.5

    async def test_exec_returns_result(self):
        bot = DummyBot(delay=0)
        method = AsyncMock(return_value="ok")
        assert await bot._exec(method, 1, a=2) == "ok"
        method.assert_awaited_once_with(1, a=2)

    async def test_exec_edit_not_found_raises_immediately(self):
        bot = DummyBot(delay=0)
        method = AsyncMock(side_effect=Exception("Message to edit not found"))
        with pytest.raises(Exception, match="edit not found"):
            await bot._exec(method)
        assert method.await_count == 1

    async def test_exec_flood_wait_retries_and_succeeds(self, monkeypatch):
        bot = DummyBot(delay=0.3, retries=3)
        monkeypatch.setattr(bot, "_throttle", AsyncMock())
        sleeps: list[float] = []
        monkeypatch.setattr(abstract, "sleep", AsyncMock(side_effect=sleeps.append))
        exc = Exception("flood")
        exc.result_json = {"parameters": {"retry_after": 12}}  # type: ignore[attr-defined]
        method = AsyncMock(side_effect=[exc, "ok"])
        assert await bot._exec(method) == "ok"
        assert sleeps == [12.0]

    async def test_exec_flood_wait_is_capped(self, monkeypatch):
        bot = DummyBot(delay=0.3, retries=1)
        monkeypatch.setattr(bot, "_throttle", AsyncMock())
        sleeps: list[float] = []
        monkeypatch.setattr(abstract, "sleep", AsyncMock(side_effect=sleeps.append))
        exc = Exception("flood")
        exc.result_json = {"parameters": {"retry_after": 7200}}  # type: ignore[attr-defined]
        method = AsyncMock(side_effect=[exc, "ok"])
        await bot._exec(method)
        assert sleeps == [abstract._FLOOD_WAIT_CAP]

    async def test_exec_flood_wait_exhausts_retries(self, monkeypatch):
        bot = DummyBot(delay=0.3, retries=1)
        monkeypatch.setattr(bot, "_throttle", AsyncMock())
        monkeypatch.setattr(abstract, "sleep", AsyncMock())
        exc = Exception("flood")
        exc.result_json = {"parameters": {"retry_after": 1}}  # type: ignore[attr-defined]
        method = AsyncMock(side_effect=exc)
        with pytest.raises(Exception, match="flood"):
            await bot._exec(method)
        assert method.await_count == 2

    async def test_exec_network_error_backs_off_exponentially(self, monkeypatch):
        bot = DummyBot(delay=0.3, retries=3)
        monkeypatch.setattr(bot, "_throttle", AsyncMock())
        sleeps: list[float] = []
        monkeypatch.setattr(abstract, "sleep", AsyncMock(side_effect=sleeps.append))
        timeout_error = type("RequestTimeout", (Exception,), {})("dns down")
        method = AsyncMock(side_effect=[timeout_error, timeout_error, "ok"])
        assert await bot._exec(method) == "ok"
        assert sleeps == [1.0, 2.0]

    async def test_exec_generic_error_uses_default_delay(self, monkeypatch):
        bot = DummyBot(delay=0.3, retries=2)
        monkeypatch.setattr(bot, "_throttle", AsyncMock())
        sleeps: list[float] = []
        monkeypatch.setattr(abstract, "sleep", AsyncMock(side_effect=sleeps.append))
        method = AsyncMock(side_effect=[ValueError("bad"), "ok"])
        assert await bot._exec(method) == "ok"
        assert sleeps == [0.3]

    async def test_exec_generic_error_exhausts_retries(self, monkeypatch):
        bot = DummyBot(delay=0.3, retries=0)
        monkeypatch.setattr(bot, "_throttle", AsyncMock())
        monkeypatch.setattr(abstract, "sleep", AsyncMock())
        with pytest.raises(ValueError, match="bad"):
            await bot._exec(AsyncMock(side_effect=ValueError("bad")))


class TestErrorClassification:
    def test_request_timeout_is_network_error(self):
        assert abstract.Bot._is_network_error(
            type("RequestTimeout", (Exception,), {})()
        )

    def test_aiohttp_connection_error_is_network_error(self):
        assert abstract.Bot._is_network_error(aiohttp.ClientConnectionError("x"))

    def test_http_response_error_is_not_network_error(self):
        assert not abstract.Bot._is_network_error(aiohttp.ClientResponseError(None, ()))

    def test_extract_retry_after_variants(self):
        exc = Exception("x")
        assert abstract.Bot._extract_retry_after(exc) is None
        exc.result_json = "not a dict"  # type: ignore[attr-defined]
        assert abstract.Bot._extract_retry_after(exc) is None
        exc.result_json = {"parameters": "nope"}  # type: ignore[attr-defined]
        assert abstract.Bot._extract_retry_after(exc) is None
        exc.result_json = {"parameters": {"retry_after": 0}}  # type: ignore[attr-defined]
        assert abstract.Bot._extract_retry_after(exc) is None
        exc.result_json = {"parameters": {"retry_after": 5}}  # type: ignore[attr-defined]
        assert abstract.Bot._extract_retry_after(exc) == 5.0


class DummyManager(abstract.Manager):
    name = "Dummy"

    def __init__(self, instance: Any = None) -> None:
        self.instance = instance
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def notify(self, chat_id: int, data: Any) -> None:
        return None


class DummyAgentic(abstract.AgenticBot):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.bot = DummyBot()
        self.log = DummyLogger()

    async def initialize(self, **kwargs: Any) -> None:
        return None

    async def start(self) -> None:
        return None


class TestAgenticBot:
    def test_init_managers_and_state(self):
        bot = DummyAgentic(managers={"m": DummyManager})
        assert isinstance(bot.managers["m"], DummyManager)
        assert bot.chat_queues == {}
        assert bot.cancel_events == {}
        assert bot.pending_media == {}
        assert bot.tts_enabled == {}

    def test_context_manager(self):
        with DummyAgentic() as bot:
            assert isinstance(bot, DummyAgentic)

    def test_prepare_handlers_binds_instance(self):
        bot = DummyAgentic()

        async def handler_func(instance: Any, value: int) -> tuple[Any, int]:
            return instance, value

        prepared = bot.prepare_handlers(chat=handler_func)
        assert prepared["chat"].func is handler_func
        assert prepared["chat"].args[0] is bot

    async def test_run_initializes_and_starts_everything(self, monkeypatch):
        started: list[str] = []

        class FakeAgent:
            @staticmethod
            async def init(dev: bool, enable_persist: bool = False) -> str:
                started.append("agent")
                return "agent-instance"

        class StartManager(DummyManager):
            async def start(self) -> None:
                started.append("manager")

        monkeypatch.setattr(abstract, "Agent", FakeAgent)
        bot = DummyAgentic(managers={"m": StartManager})

        async def initialize(**kwargs: Any) -> None:
            started.append("bot-init")

        async def start() -> None:
            started.append("bot-start")

        bot.bot.initialize = initialize  # type: ignore[method-assign]
        bot.bot.start = start  # type: ignore[method-assign]
        await bot.run(chat=AsyncMock())
        assert started[:2] == ["agent", "bot-init"]
        assert set(started[2:]) == {"bot-start", "manager"}
        assert bot.agent == "agent-instance"

    async def test_run_handles_keyboard_interrupt(self, monkeypatch, caplog):
        class FakeAgent:
            @staticmethod
            async def init(dev: bool, enable_persist: bool = False) -> str:
                return "agent-instance"

        def interrupting_gather(*aws: Any, **kwargs: Any) -> None:
            for aw in aws:
                aw.close()
            raise KeyboardInterrupt

        monkeypatch.setattr(abstract, "Agent", FakeAgent)
        # A real Ctrl-C surfaces while awaiting gather(), not inside a child
        # task (raising it in a task would stop the loop instead).
        monkeypatch.setattr(abstract, "gather", interrupting_gather)
        bot = DummyAgentic()
        await bot.run()
        assert "killed by KeyboardInterrupt" in caplog.text

    async def test_run_logs_unexpected_errors(self, monkeypatch, caplog):
        class FakeAgent:
            @staticmethod
            async def init(dev: bool, enable_persist: bool = False) -> str:
                return "agent-instance"

        class ExplodingBot(DummyBot):
            async def initialize(self, **kwargs: Any) -> None:
                raise RuntimeError("boom")

        monkeypatch.setattr(abstract, "Agent", FakeAgent)
        bot = DummyAgentic()
        bot.bot = ExplodingBot()
        await bot.run()
        assert "Error running bot" in caplog.text


class TestHandlerDecorator:
    async def test_registers_interaction_when_message_like(self, monkeypatch):
        registered: list[Any] = []
        monkeypatch.setattr(
            abstract,
            "register_interaction",
            lambda msg, bot=None: registered.append((msg, bot)),
        )

        @abstract.handler
        async def h(instance: Any, msg: Any) -> str:
            return "handled"

        msg = type("M", (), {"chat": object()})()
        instance = DummyAgentic()
        assert await h(instance, msg) == "handled"
        assert registered
        assert registered[0][0] is msg

    async def test_skips_registration_without_message(self, monkeypatch):
        registered: list[Any] = []
        monkeypatch.setattr(
            abstract, "register_interaction", lambda *a, **k: registered.append(1)
        )

        @abstract.handler
        async def h(instance: Any) -> str:
            return "handled"

        await h(DummyAgentic())
        assert registered == []
