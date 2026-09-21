"""Tests for ``telegram_agent/src/bot/handlers/telegram.py``."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from telegram_agent.src.bot.handlers import telegram as h
from telegram_agent.tests.fakes import FakeAgent, FakeInstance, make_message


class FakeChatLLM:
    def __init__(self, text: str = "result") -> None:
        self.text = text

    async def ainvoke(self, messages: Any) -> AIMessage:
        return AIMessage(self.text)


@pytest.fixture(autouse=True)
def _clean_media_groups():
    h._media_groups.clear()
    yield
    h._media_groups.clear()


def patch_llm(
    monkeypatch, *, helper: str | None = "helper", text: str = "result"
) -> Any:
    fake_llm = FakeChatLLM(text)
    monkeypatch.setattr(
        h,
        "LLM",
        SimpleNamespace(
            pick=staticmethod(lambda *caps, **kw: helper),
            get=staticmethod(lambda p=None: fake_llm),
        ),
    )
    return fake_llm


class TestVoiceTimestamps:
    def test_bracketed_and_plain_timestamps_removed(self):
        text = "[00:01] Hello  00:15 world (1:02:03) end"
        assert h._strip_voice_timestamps(text) == "Hello world end"

    def test_clean_text_untouched(self):
        assert h._strip_voice_timestamps("just words") == "just words"


class TestImagePersistence:
    async def test_save_and_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(h, "_RECEIVED_DIR", tmp_path)
        path = await h._save_received_image(b"\x00\x01")
        assert path.endswith(".jpg")
        assert await h._read_image(path) == b"\x00\x01"


class TestMediaToText:
    async def test_audio_uses_stt_and_strips_timestamps(self, monkeypatch):
        patch_llm(monkeypatch, helper="helper", text="[00:01] spoken words")
        out = await h._media_to_text([{"mime_type": "audio/ogg"}])
        assert out == "spoken words"

    async def test_image_uses_vision(self, monkeypatch):
        patch_llm(monkeypatch, helper="helper", text='{"subject": "x"}')
        out = await h._media_to_text([{"mime_type": "image/jpeg"}])
        assert out == '{"subject": "x"}'

    async def test_no_capable_provider(self, monkeypatch):
        patch_llm(monkeypatch, helper=None)
        assert "no stt-capable provider" in await h._media_to_text(
            [{"mime_type": "audio/ogg"}]
        )
        assert "no vision-capable provider" in await h._media_to_text(
            [{"mime_type": "image/jpeg"}]
        )


class TestUserAdmin:
    def make(self, admin: bool = False) -> FakeInstance:
        return FakeInstance(agent=FakeAgent(allowed={"1": "One"}, admin={"9": "Boss"}))

    def test_allow_user_usage_error(self):
        instance = self.make()
        assert h._user_admin(instance, "/allow-user nope").startswith("⚠️ Usage")

    def test_allow_user_adds_and_persists(self):
        instance = self.make()
        out = h._user_admin(instance, "/allow-user@mybot 5=Five")
        assert "Five (5) can now talk" in out
        assert instance.agent.is_allowed(5)

    def test_ban_user_validation_and_admin_protection(self):
        instance = self.make()
        assert h._user_admin(instance, "/ban-user abc").startswith("⚠️ Usage")
        assert h._user_admin(instance, "/ban-user 9") == "⚠️ Can't ban an admin."
        assert h._user_admin(instance, "/ban-user 7") == (
            "⚠️ 7 is not in the allowed list."
        )

    def test_ban_user_removes(self):
        instance = self.make()
        assert (
            h._user_admin(instance, "/ban-user 1") == "🚫 1 can no longer talk to me."
        )
        assert not instance.agent.is_allowed(1)

    def test_list_users(self):
        instance = self.make()
        out = h._user_admin(instance, "/list-user")
        assert "👑 Admin:\n  9: Boss" in out
        assert "👥 Allowed:\n  1: One" in out

    def test_list_users_alias_and_empty_groups(self):
        instance = self.make(admin=True)
        instance.agent.user_config = {}
        out = h._user_admin(instance, "/list-users")
        assert "(none)" in out

    def test_unknown_command(self):
        assert "Unknown user command" in h._user_admin(self.make(), "/nope")


class TestReportIssue:
    async def test_reports_to_admin_and_user(self, monkeypatch):
        monkeypatch.setattr(h, "TELEGRAM_CHAT_DEV", "999")
        instance = FakeInstance()
        orig = make_message("x", chat_id=1)
        reply = make_message("r", chat_id=1)
        await h.telegram_report_issue(instance, orig, reply, RuntimeError("boom"))
        assert instance.bot.sent
        assert instance.bot.sent[0][0] == "999"
        assert instance.bot.replies
        assert any(level == "error" for level, _ in instance.log.events)

    async def test_skips_user_reply_in_dev_chat(self, monkeypatch):
        monkeypatch.setattr(h, "TELEGRAM_CHAT_DEV", "1")
        instance = FakeInstance()
        msg = make_message("x", chat_id=1)
        await h.telegram_report_issue(instance, msg, msg, "agent failure")
        assert instance.bot.sent
        assert instance.bot.replies == []

    async def test_no_dev_chat_no_admin_send(self, monkeypatch):
        monkeypatch.setattr(h, "TELEGRAM_CHAT_DEV", None)
        instance = FakeInstance()
        msg = make_message("x", chat_id=1)
        await h.telegram_report_issue(instance, msg, msg, "oops")
        assert instance.bot.sent == []
        assert instance.bot.replies


class TestTelegramChat:
    async def test_rejects_disallowed_user(self):
        instance = FakeInstance(agent=FakeAgent(allowed={"1": "One"}))
        await h.telegram_chat(instance, make_message(user_id=99))
        assert instance.chat_queues == {}
        assert instance.bot.sent == []

    async def test_rejects_missing_sender(self):
        instance = FakeInstance()
        await h.telegram_chat(instance, make_message(from_user=False))
        assert instance.chat_queues == {}

    async def test_start_and_help_reply(self):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        await h.telegram_chat(instance, make_message("/start"))
        assert "Welcome" in instance.bot.sent[0][1]
        await h.telegram_chat(instance, make_message("/help"))
        assert len(instance.bot.sent) == 2

    async def test_tts_toggle(self):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        await h.telegram_chat(instance, make_message("/tts"))
        assert instance.tts_enabled[456] is True
        assert "on 🔊" in instance.bot.sent[0][1]
        await h.telegram_chat(instance, make_message("/tts"))
        assert instance.tts_enabled[456] is False
        assert "off 🔇" in instance.bot.sent[1][1]

    async def test_admin_commands_gated(self):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        await h.telegram_chat(instance, make_message("/list-user"))
        assert instance.bot.sent == []
        instance.agent.user_config["admin"] = {"users": {"456": "Tester"}}
        await h.telegram_chat(instance, make_message("/list-user"))
        assert "👑 Admin:" in instance.bot.sent[0][1]

    async def test_cancel_with_and_without_running_turn(self):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        await h.telegram_chat(instance, make_message("/cancel"))
        assert instance.bot.sent[0][1] == "Nothing to cancel."
        event = MagicMock()
        instance.cancel_events[123] = event
        await h.telegram_chat(instance, make_message("/cancel"))
        event.set.assert_called_once()

    async def test_message_enqueued_and_worker_started(self, monkeypatch):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        closed: list[Any] = []

        def fake_create_task(coro: Any) -> Any:
            closed.append(coro)
            coro.close()
            return SimpleNamespace(done=lambda: False)

        monkeypatch.setattr(h, "create_task", fake_create_task)
        await h.telegram_chat(instance, make_message("hello"))
        assert instance.chat_queues[123].qsize() == 1
        assert closed
        assert 123 in instance.chat_workers

    async def test_new_message_supersedes_active_turn(self, monkeypatch):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        monkeypatch.setattr(h, "create_task", lambda coro: _closed_task(coro))
        active = MagicMock()
        instance.cancel_events[123] = active
        instance.chat_workers[123] = _closed_task(_noop())
        await h.telegram_chat(instance, make_message("more"))
        active.set.assert_called_once()

    async def test_group_trigger_left_to_bot_wrapper(self, monkeypatch):
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        monkeypatch.setattr(h, "create_task", lambda coro: _closed_task(coro))
        msg = make_message("!do it", chat_type="group")
        await h.telegram_chat(instance, msg)
        queued, _, _ = instance.chat_queues[123].get_nowait()
        assert queued.text == "!do it"


async def _noop() -> None:
    return None


def _closed_task(coro: Any) -> Any:
    coro.close()
    return SimpleNamespace(done=lambda: False)


class TestChatWorker:
    async def test_drains_queue_and_cleans_up(self, monkeypatch):
        from asyncio import Queue

        instance = FakeInstance()
        ran: list[Any] = []

        async def fake_run_turn(
            inst: Any, msg: Any, overwrite: Any, timer: Any
        ) -> None:
            ran.append(msg)

        monkeypatch.setattr(h, "_run_turn", fake_run_turn)
        queue: Queue[Any] = Queue()
        queue.put_nowait(("msg", None, "timer"))
        instance.chat_queues[123] = queue
        await h._chat_worker(instance, 123)
        assert ran == ["msg"]
        assert 123 not in instance.chat_queues
        assert 123 not in instance.chat_workers


class TestRunTurn:
    def make_instance(self, events: list[tuple[Any, ...]]) -> FakeInstance:
        return FakeInstance(
            agent=FakeAgent(allowed={"456": "Tester"}, chat_events=events)
        )

    async def test_final_event_edits_message(self, monkeypatch):
        instance = self.make_instance([("A", "hello", True, {})])
        msg = make_message("hi")
        await h._run_turn(instance, msg, None, instance.log.received(msg))
        assert instance.bot.edits
        assert instance.bot.edits[-1][1] == "hello"
        assert instance.bot.edits[-1][2]["final"] is True

    async def test_tool_success_notifies_manager(self, monkeypatch):
        manager = SimpleNamespace(notify=AsyncMock())
        instance = self.make_instance([("A", "🛠️ Tool...", False, {"tool_block": True})])
        instance.managers["torrent_client"] = manager
        events = [
            (
                "A",
                "✅ Something",
                False,
                {"tool": "torrent_client", "tool_ok": True, "tool_block": True},
            )
        ]
        instance.agent.chat_events = events
        msg = make_message("hi")
        monkeypatch.setattr(h, "sleep", AsyncMock())
        await h._run_turn(instance, msg, None, instance.log.received(msg))
        manager.notify.assert_awaited_once()

    async def test_tool_error_reports_issue(self, monkeypatch):
        instance = self.make_instance(
            [("A", "❌ Bad", False, {"tool": "x", "tool_ok": False})]
        )
        report = AsyncMock()
        monkeypatch.setattr(h, "telegram_report_issue", report)
        msg = make_message("hi")
        await h._run_turn(instance, msg, None, instance.log.received(msg))
        report.assert_awaited_once()

    async def test_agent_exception_reports_issue(self, monkeypatch):
        class ExplodingAgent(FakeAgent):
            async def chat(self, content: Any):
                raise RuntimeError("agent down")
                yield  # pragma: no cover

        instance = FakeInstance(agent=ExplodingAgent())
        report = AsyncMock()
        monkeypatch.setattr(h, "telegram_report_issue", report)
        msg = make_message("hi")
        await h._run_turn(instance, msg, None, instance.log.received(msg))
        report.assert_awaited_once()
        assert 123 not in instance.cancel_events

    async def test_images_are_sent_after_completion(self, tmp_path):
        image = tmp_path / "img.png"
        image.write_bytes(b"PNG")
        instance = self.make_instance([("A", "done", True, {"images": [str(image)]})])
        await h._run_turn(instance, make_message("hi"), None, "timer")
        calls = [name for name, _, _ in instance.bot.core.calls]
        assert "send_chat_action" in calls
        assert "send_photo" in calls

    async def test_multiple_images_use_media_group(self, tmp_path):
        paths = []
        for i in range(2):
            path = tmp_path / f"{i}.png"
            path.write_bytes(b"PNG")
            paths.append(str(path))
        instance = self.make_instance([("A", "done", True, {"images": paths})])
        await h._run_turn(instance, make_message("hi"), None, "timer")
        calls = [name for name, _, _ in instance.bot.core.calls]
        assert "send_media_group" in calls

    async def test_pending_media_attached_when_main_can_see(self, monkeypatch):
        instance = self.make_instance([("A", "done", True, {})])
        instance.pending_media[123] = [(b"IMG", "/tmp/x.jpg")]
        monkeypatch.setattr(
            h, "LLM", SimpleNamespace(pick=staticmethod(lambda *a, **k: "p"))
        )
        monkeypatch.setattr(h, "can_see", lambda p: True)
        msg = make_message("hi")
        await h._run_turn(instance, msg, None, "timer")
        assert msg.media
        assert "[Received image files:]" in msg.text

    async def test_pending_media_described_when_no_vision(self, monkeypatch, tmp_path):
        instance = self.make_instance([("A", "done", True, {})])
        img_path = tmp_path / "x.jpg"
        img_path.write_bytes(b"IMG")
        instance.pending_media[123] = [(b"IMG", str(img_path))]
        monkeypatch.setattr(
            h, "LLM", SimpleNamespace(pick=staticmethod(lambda *a, **k: "p"))
        )
        monkeypatch.setattr(h, "can_see", lambda p: False)
        describe = AsyncMock(return_value='{"desc": "x"}')
        monkeypatch.setattr(h, "_media_to_text", describe)
        msg = make_message("hi")
        await h._run_turn(instance, msg, None, "timer")
        describe.assert_awaited_once()
        assert (tmp_path / "x_desc.json").exists()
        assert "[Received images:]" in msg.text

    async def test_cancel_interrupts_turn(self, monkeypatch):
        instance = self.make_instance([])
        monkeypatch.setattr(h, "sleep", AsyncMock())

        class CancellingAgent(FakeAgent):
            async def chat(self, content: Any):
                yield ("A", "step one", False, {})
                instance.cancel_events[123].set()
                yield ("A", "never", True, {})

        instance.agent = CancellingAgent()
        await h._run_turn(instance, make_message("hi"), None, "timer")
        assert any(edit[1] == "⏹️ Interrompu" for edit in instance.bot.edits)

    async def test_completed_turn_sends_tts_voice(self, monkeypatch):
        instance = self.make_instance([("A", "final", True, {})])
        instance.tts_enabled[456] = True

        async def fake_exec(*args: Any, **kwargs: Any) -> Any:
            async def communicate(data: bytes) -> tuple[bytes, bytes]:
                return b"OGG", b""

            return SimpleNamespace(communicate=communicate, returncode=0)

        monkeypatch.setattr(h, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(
            h,
            "LLM",
            SimpleNamespace(
                pick=staticmethod(lambda *caps, **kw: "tts"),
                tts_adapt=staticmethod(AsyncMock(return_value="spoken")),
                tts=staticmethod(AsyncMock(return_value=b"AUDIO")),
            ),
        )
        await h._run_turn(instance, make_message("hi"), None, "timer")
        calls = [name for name, _, _ in instance.bot.core.calls]
        assert "send_voice" in calls
        assert not any(edit[1] == "⏹️ Interrompu" for edit in instance.bot.edits)

    async def test_completed_turn_tts_failure_reports(self, monkeypatch):
        instance = self.make_instance([("A", "final", True, {})])
        instance.tts_enabled[456] = True
        monkeypatch.setattr(
            h,
            "LLM",
            SimpleNamespace(
                pick=staticmethod(lambda *caps, **kw: "tts"),
                tts_adapt=staticmethod(AsyncMock(return_value="spoken")),
                tts=staticmethod(AsyncMock(return_value=None)),
            ),
        )
        await h._run_turn(instance, make_message("hi"), None, "timer")
        assert any("TTS failed" in (sent[1] or "") for sent in instance.bot.sent)
        assert all(name != "send_voice" for name, _, _ in instance.bot.core.calls)

    async def test_cancelled_turn_sends_no_tts(self, monkeypatch):
        instance = self.make_instance([])
        monkeypatch.setattr(h, "sleep", AsyncMock())

        class CancellingAgent(FakeAgent):
            async def chat(self, content: Any):
                yield ("A", "step one", False, {})
                instance.cancel_events[123].set()
                yield ("A", "never", True, {})

        instance.agent = CancellingAgent()
        instance.tts_enabled[456] = True
        monkeypatch.setattr(
            h,
            "LLM",
            SimpleNamespace(
                pick=staticmethod(lambda *caps, **kw: "tts"),
                tts_adapt=staticmethod(AsyncMock(return_value="spoken")),
                tts=staticmethod(AsyncMock(return_value=b"AUDIO")),
            ),
        )
        await h._run_turn(instance, make_message("hi"), None, "timer")
        assert any(edit[1] == "⏹️ Interrompu" for edit in instance.bot.edits)
        assert all(name != "send_voice" for name, _, _ in instance.bot.core.calls)

    async def test_empty_stream_with_tts_enabled_does_not_raise(self, monkeypatch):
        instance = self.make_instance([])
        instance.tts_enabled[456] = True
        monkeypatch.setattr(
            h,
            "LLM",
            SimpleNamespace(pick=staticmethod(lambda *caps, **kw: "tts")),
        )
        await h._run_turn(instance, make_message("hi"), None, "timer")
        assert all(name != "send_voice" for name, _, _ in instance.bot.core.calls)


class TestVoiceHandler:
    def make_instance(self, listen: bool = True) -> FakeInstance:
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        return instance

    async def test_voice_queued_with_audio_media(self, monkeypatch):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock(
            return_value=SimpleNamespace(file_path="voice.ogg")
        )
        instance.bot.core.download_file = AsyncMock(return_value=b"AUDIO")
        monkeypatch.setattr(
            h, "LLM", SimpleNamespace(pick=staticmethod(lambda *a, **k: "p"))
        )
        monkeypatch.setattr(h, "can_listen", lambda p: True)
        chat = AsyncMock()
        monkeypatch.setattr(h, "telegram_chat", chat)
        msg = make_message(
            "", voice={"file_id": "v", "file_unique_id": "u", "duration": 1}
        )
        await h.telegram_voice(instance, msg)
        chat.assert_awaited_once()
        assert msg.media[0]["data"] == b"AUDIO"

    async def test_voice_transcribed_when_no_stt(self, monkeypatch):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock(
            return_value=SimpleNamespace(file_path="voice.ogg")
        )
        instance.bot.core.download_file = AsyncMock(return_value=b"AUDIO")
        monkeypatch.setattr(
            h, "LLM", SimpleNamespace(pick=staticmethod(lambda *a, **k: "p"))
        )
        monkeypatch.setattr(h, "can_listen", lambda p: False)
        monkeypatch.setattr(h, "_media_to_text", AsyncMock(return_value="hello"))
        chat = AsyncMock()
        monkeypatch.setattr(h, "telegram_chat", chat)
        msg = make_message(
            "", voice={"file_id": "v", "file_unique_id": "u", "duration": 1}
        )
        await h.telegram_voice(instance, msg)
        assert msg.text == "🎤 hello"

    async def test_voice_without_payload_returns(self):
        instance = self.make_instance()
        await h.telegram_voice(instance, make_message("voice"))
        assert instance.bot.sent == []

    async def test_ogg_document_queued_with_audio_media(self, monkeypatch):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock(
            return_value=SimpleNamespace(file_path="note.ogg")
        )
        instance.bot.core.download_file = AsyncMock(return_value=b"AUDIO")
        monkeypatch.setattr(
            h, "LLM", SimpleNamespace(pick=staticmethod(lambda *a, **k: "p"))
        )
        monkeypatch.setattr(h, "can_listen", lambda p: True)
        chat = AsyncMock()
        monkeypatch.setattr(h, "telegram_chat", chat)
        msg = make_message(
            "",
            document={
                "file_id": "d",
                "file_unique_id": "u",
                "file_name": "note.ogg",
                "mime_type": "audio/ogg",
            },
        )
        await h.telegram_voice(instance, msg)
        chat.assert_awaited_once()
        assert msg.media[0]["data"] == b"AUDIO"
        assert msg.media[0]["mime_type"] == "audio/ogg"

    async def test_audio_file_transcribed_with_its_mime(self, monkeypatch):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock(
            return_value=SimpleNamespace(file_path="song.mp3")
        )
        instance.bot.core.download_file = AsyncMock(return_value=b"AUDIO")
        monkeypatch.setattr(
            h, "LLM", SimpleNamespace(pick=staticmethod(lambda *a, **k: "p"))
        )
        monkeypatch.setattr(h, "can_listen", lambda p: False)
        transcribe = AsyncMock(return_value="paroles")
        monkeypatch.setattr(h, "_transcribe_voice", transcribe)
        chat = AsyncMock()
        monkeypatch.setattr(h, "telegram_chat", chat)
        msg = make_message(
            "",
            audio={
                "file_id": "a",
                "file_unique_id": "u",
                "duration": 12,
                "mime_type": "audio/mpeg",
            },
        )
        await h.telegram_voice(instance, msg)
        transcribe.assert_awaited_once_with(b"AUDIO", 12, "audio/mpeg")
        assert msg.text == "🎤 paroles"

    async def test_non_audio_document_ignored(self):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock()
        instance.bot.core.download_file = AsyncMock()
        msg = make_message(
            "",
            document={
                "file_id": "d",
                "file_unique_id": "u",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
            },
        )
        await h.telegram_voice(instance, msg)
        assert instance.bot.sent == []
        instance.bot.core.get_file.assert_not_awaited()

    async def test_voice_error_reported(self, monkeypatch):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock(side_effect=RuntimeError("boom"))
        report = AsyncMock()
        monkeypatch.setattr(h, "telegram_report_issue", report)
        await h.telegram_voice(
            instance,
            make_message(
                "", voice={"file_id": "v", "file_unique_id": "u", "duration": 1}
            ),
        )
        report.assert_awaited_once()


class TestImageHandler:
    def make_instance(self) -> FakeInstance:
        instance = FakeInstance(agent=FakeAgent(allowed={"456": "Tester"}))
        instance.bot.core.get_file = AsyncMock(
            return_value=SimpleNamespace(file_path="photo.jpg")
        )
        instance.bot.core.download_file = AsyncMock(return_value=b"IMG")
        return instance

    async def test_caption_queues_turn(self, monkeypatch, tmp_path):
        instance = self.make_instance()
        monkeypatch.setattr(
            h, "_save_received_image", AsyncMock(return_value=str(tmp_path / "x.jpg"))
        )
        chat = AsyncMock()
        monkeypatch.setattr(h, "telegram_chat", chat)
        msg = make_message(
            "",
            photo=[{"file_id": "p", "file_unique_id": "u", "width": 1, "height": 1}],
            caption="look",
        )
        await h.telegram_image(instance, msg)
        chat.assert_awaited_once()
        assert instance.pending_media[123]
        assert msg.text == "look"

    async def test_no_caption_store_for_later(self, monkeypatch, tmp_path):
        instance = self.make_instance()
        monkeypatch.setattr(
            h, "_save_received_image", AsyncMock(return_value=str(tmp_path / "x.jpg"))
        )
        msg = make_message(
            "", photo=[{"file_id": "p", "file_unique_id": "u", "width": 1, "height": 1}]
        )
        await h.telegram_image(instance, msg)
        assert instance.pending_media[123]
        assert any("Got it!" in edit[1] for edit in instance.bot.edits)

    async def test_album_processed_once(self, monkeypatch, tmp_path):
        instance = self.make_instance()
        monkeypatch.setattr(
            h, "_save_received_image", AsyncMock(return_value=str(tmp_path / "x.jpg"))
        )
        monkeypatch.setattr(h, "sleep", AsyncMock())
        msg = make_message(
            "",
            photo=[{"file_id": "p", "file_unique_id": "u", "width": 1, "height": 1}],
            media_group_id="g1",
            caption="album",
        )
        chat = AsyncMock()
        monkeypatch.setattr(h, "telegram_chat", chat)
        await h.telegram_image(instance, msg)
        chat.assert_awaited_once()
        assert h._media_groups == {}

    async def test_error_reported_and_group_cleaned(self, monkeypatch):
        instance = self.make_instance()
        instance.bot.core.get_file = AsyncMock(side_effect=RuntimeError("boom"))
        report = AsyncMock()
        monkeypatch.setattr(h, "telegram_report_issue", report)
        h._media_groups["g2"] = {"images": [], "msg": None, "reply": None}
        msg = make_message(
            "",
            photo=[{"file_id": "p", "file_unique_id": "u", "width": 1, "height": 1}],
            media_group_id="g2",
        )
        await h.telegram_image(instance, msg)
        report.assert_awaited_once()
        assert "g2" not in h._media_groups


class TestVoiceTranscription:
    """Long voice notes are segmented and length-checked.

    The STT helper intermittently returns a fraction of a long transcript;
    segments below ~10 chars per audio second are retried with the main model
    and the longest attempt wins.
    """

    def pcm(self, seconds: float) -> bytes:
        return bytes(int(h._STT_PCM_RATE * 2 * seconds))

    def test_wav_segments_split_into_self_contained_files(self, monkeypatch):
        monkeypatch.setattr(h, "_STT_SEGMENT_SECONDS", 1)
        segments = h._wav_segments(self.pcm(2.5))
        assert [round(secs, 2) for _, secs in segments] == [1.0, 1.0, 0.5]
        for data, _ in segments:
            assert data[:4] == b"RIFF"
            assert data[8:12] == b"WAVE"

    async def test_short_voice_note_keeps_single_call(self, monkeypatch):
        monkeypatch.setattr(h, "_STT_MIN_CHARS_PER_SECOND", 0.0)
        transcribe = AsyncMock(return_value="bonjour")
        monkeypatch.setattr(h, "_media_to_text", transcribe)
        out = await h._transcribe_voice(b"OGG", duration=10)
        assert out == "bonjour"
        transcribe.assert_awaited_once()
        assert transcribe.await_args.args[0][0]["mime_type"] == "audio/ogg"

    async def test_long_voice_note_is_segmented_and_joined(self, monkeypatch):
        monkeypatch.setattr(h, "_STT_SEGMENT_SECONDS", 1)
        monkeypatch.setattr(h, "_decode_pcm", AsyncMock(return_value=self.pcm(2.5)))
        transcribe = AsyncMock(
            side_effect=["un deux trois", "quatre cinq six", "sept huit"]
        )
        monkeypatch.setattr(h, "_media_to_text", transcribe)
        out = await h._transcribe_voice(b"OGG", duration=2.5)
        assert out == "un deux trois quatre cinq six sept huit"
        assert transcribe.await_count == 3
        assert all(
            call.args[0][0]["mime_type"] == "audio/wav"
            for call in transcribe.await_args_list
        )

    async def test_document_audio_decodes_once_and_segments(self, monkeypatch):
        monkeypatch.setattr(h, "_STT_SEGMENT_SECONDS", 1)
        decode = AsyncMock(return_value=self.pcm(2.5))
        monkeypatch.setattr(h, "_decode_pcm", decode)
        transcribe = AsyncMock(
            side_effect=["un deux trois", "quatre cinq six", "sept huit"]
        )
        monkeypatch.setattr(h, "_media_to_text", transcribe)
        out = await h._transcribe_voice(b"OGG", None, "audio/ogg")
        assert out == "un deux trois quatre cinq six sept huit"
        decode.assert_awaited_once()
        assert transcribe.await_count == 3

    async def test_document_audio_short_keeps_its_mime(self, monkeypatch):
        monkeypatch.setattr(h, "_STT_MIN_CHARS_PER_SECOND", 0.0)
        decode = AsyncMock(return_value=self.pcm(5))
        monkeypatch.setattr(h, "_decode_pcm", decode)
        transcribe = AsyncMock(return_value="bonjour")
        monkeypatch.setattr(h, "_media_to_text", transcribe)
        out = await h._transcribe_voice(b"OGG", None, "audio/mpeg")
        assert out == "bonjour"
        transcribe.assert_awaited_once()
        assert transcribe.await_args.args[0][0]["mime_type"] == "audio/mpeg"

    async def test_truncated_segment_is_retried_with_main_model(self, monkeypatch):
        calls = []

        async def fake(media, context="", fast=True):
            calls.append(fast)
            return "court" if len(calls) == 1 else "x" * 120

        monkeypatch.setattr(h, "_media_to_text", fake)
        out = await h._transcribe_segment(b"A", "audio/wav", duration=10)
        assert calls == [True, False]
        assert out == "x" * 120

    async def test_decode_failure_falls_back_to_single_ogg_call(self, monkeypatch):
        monkeypatch.setattr(h, "_STT_MIN_CHARS_PER_SECOND", 0.0)
        monkeypatch.setattr(
            h, "_decode_pcm", AsyncMock(side_effect=RuntimeError("no ffmpeg"))
        )
        transcribe = AsyncMock(return_value="texte")
        monkeypatch.setattr(h, "_media_to_text", transcribe)
        out = await h._transcribe_voice(b"OGG", duration=600)
        assert out == "texte"
        transcribe.assert_awaited_once()
        assert transcribe.await_args.args[0][0]["mime_type"] == "audio/ogg"

    async def test_all_attempts_failing_raises_last_error(self, monkeypatch):
        async def boom(media, context="", fast=True):
            raise RuntimeError("provider down")

        monkeypatch.setattr(h, "_media_to_text", boom)
        with pytest.raises(RuntimeError, match="provider down"):
            await h._transcribe_segment(b"A", "audio/ogg", duration=10)
