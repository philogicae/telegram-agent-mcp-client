"""Tests for ``telegram_agent/src/bot/relay.py``."""

from json import loads
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from telegram_agent.src.bot import relay
from telegram_agent.tests.fakes import FakeInstance


class FakeRequest:
    def __init__(self, body: str = "", headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def text(self) -> str:
        return self._body


def body_of(response: Any) -> dict[str, Any]:
    return loads(response.body.decode())


@pytest.fixture
def instance() -> FakeInstance:
    instance = FakeInstance()
    instance.bot.send = AsyncMock()
    return instance


class TestHandleRelay:
    async def test_no_token_configured_is_unauthorized(self, monkeypatch, instance):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", None)
        response = await relay._handle_relay(instance, FakeRequest())
        assert response.status == 401
        assert body_of(response) == {"error": "unauthorized"}

    async def test_wrong_token_is_unauthorized(self, monkeypatch, instance):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", "secret")
        request = FakeRequest(headers={"X-Relay-Token": "wrong"})
        response = await relay._handle_relay(instance, request)
        assert response.status == 401

    async def test_invalid_json_rejected(self, monkeypatch, instance):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", "secret")
        request = FakeRequest(body="{not json", headers={"X-Relay-Token": "secret"})
        response = await relay._handle_relay(instance, request)
        assert response.status == 400

    async def test_missing_fields_rejected(self, monkeypatch, instance):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", "secret")
        request = FakeRequest(
            body='{"chat_id": 1}', headers={"X-Relay-Token": "secret"}
        )
        assert (await relay._handle_relay(instance, request)).status == 400
        request = FakeRequest(
            body='{"chat_id": 1, "sender": " ", "prompt": "x"}',
            headers={"X-Relay-Token": "secret"},
        )
        assert (await relay._handle_relay(instance, request)).status == 400

    async def test_valid_payload_dispatches_turn(self, monkeypatch, instance):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", "secret")
        scheduled: list[Any] = []
        chat = AsyncMock()
        monkeypatch.setattr(relay, "telegram_chat", chat)

        def fake_create_task(coro: Any) -> Any:
            scheduled.append(coro)
            coro.close()
            return SimpleNamespace(add_done_callback=lambda cb: None)

        monkeypatch.setattr(relay, "create_task", fake_create_task)
        request = FakeRequest(
            body='{"chat_id": 42, "sender": "webapp", "prompt": "approve", "notice": "New request"}',
            headers={"X-Relay-Token": "secret"},
        )
        response = await relay._handle_relay(instance, request)
        assert response.status == 200
        assert body_of(response) == {"status": "accepted"}
        instance.bot.send.assert_awaited_once_with(42, "New request")
        assert scheduled
        assert any(level == "info" for level, _ in instance.log.events)

    async def test_valid_payload_without_notice(self, monkeypatch, instance):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", "secret")
        monkeypatch.setattr(
            relay,
            "create_task",
            lambda coro: _closed(coro),
        )
        request = FakeRequest(
            body='{"chat_id": 42, "sender": "webapp", "prompt": "approve"}',
            headers={"X-Relay-Token": "secret"},
        )
        await relay._handle_relay(instance, request)
        instance.bot.send.assert_not_awaited()


def _closed(coro: Any) -> Any:
    coro.close()
    return SimpleNamespace(add_done_callback=lambda cb: None)


class TestLogTaskFailure:
    def test_exception_logged(self):
        instance = FakeInstance()
        task = SimpleNamespace(
            cancelled=lambda: False, exception=lambda: RuntimeError("boom")
        )
        relay._log_task_failure(instance, task)
        assert any(level == "exception" for level, _ in instance.log.events)

    def test_success_and_cancelled_are_silent(self):
        instance = FakeInstance()
        relay._log_task_failure(
            instance, SimpleNamespace(cancelled=lambda: False, exception=lambda: None)
        )
        relay._log_task_failure(
            instance, SimpleNamespace(cancelled=lambda: True, exception=lambda: None)
        )
        assert instance.log.events == []


class TestApp:
    def test_start_relay_requires_token(self, monkeypatch):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", None)
        assert relay.start_relay(FakeInstance()) is None

    def test_start_relay_builds_app(self, monkeypatch):
        monkeypatch.setattr(relay, "_RELAY_TOKEN", "secret")
        app = relay.start_relay(FakeInstance())
        assert app is not None
        assert list(app.router.routes())

    async def test_serve_starts_site_then_waits(self, monkeypatch):
        started: list[Any] = []

        class FakeRunner:
            def __init__(self, app: Any) -> None:
                self.app = app

            async def setup(self) -> None:
                started.append("setup")

        class FakeSite:
            def __init__(self, runner: Any, host: str, port: int) -> None:
                started.append(("site", host, port))

            async def start(self) -> None:
                started.append("start")

        class FakeEvent:
            async def wait(self) -> None:
                started.append("wait")

        monkeypatch.setattr(relay.web, "AppRunner", FakeRunner)
        monkeypatch.setattr(relay.web, "TCPSite", FakeSite)
        monkeypatch.setattr(relay, "Event", FakeEvent)
        await relay.serve(object())
        assert started == [
            "setup",
            ("site", "0.0.0.0", relay._RELAY_PORT),
            "start",
            "wait",
        ]
