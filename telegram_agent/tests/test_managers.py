"""Tests for the torrent manager."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_agent.src.bot.managers import torrents as torrents_mod
from telegram_agent.src.bot.managers.torrents import (
    DownloadManager,
    Torrent,
)
from telegram_agent.src.bot.managers.torrents import (
    Message as DownloadMessage,
)
from telegram_agent.tests.fakes import FakeInstance


class _Stop(Exception):
    pass


def make_torrent(**kwargs: Any) -> Torrent:
    values: dict[str, Any] = {"name": "Release"}
    values.update(kwargs)
    return Torrent(**values)


def make_download_manager() -> tuple[DownloadManager, FakeInstance]:
    instance = FakeInstance()
    manager = DownloadManager(instance, delay=0)
    manager.client = MagicMock()
    manager.client.get_torrent = AsyncMock()
    manager.client.remove_torrent = AsyncMock(return_value=None)
    return manager, instance


class TestTorrentModel:
    def test_nearly_done(self):
        assert make_torrent(stats={"percentDone": 0.96}).nearly_done
        assert not make_torrent(stats={"percentDone": 0.5}).nearly_done
        assert not make_torrent().nearly_done


class TestDownloadNotify:
    async def test_notify_tracks_new_torrent(self):
        manager, instance = make_download_manager()
        await manager.notify(1, '{"hashString": "h1", "name": "N"}')
        assert "h1" in manager.torrents
        assert manager.chats[1].torrent_ids == {"h1"}

    async def test_notify_without_hash_logs_error(self):
        manager, instance = make_download_manager()
        await manager.notify(1, '{"name": "N"}')
        assert manager.torrents == {}
        assert any(level == "error" for level, _ in instance.log.events)

    async def test_notify_revives_done_torrent(self):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent(done=True)
        await manager.notify(1, '{"infoHash": "h1", "name": "N"}')
        assert not manager.torrents["h1"].done

    async def test_notify_recreates_message(self):
        manager, instance = make_download_manager()
        old = SimpleNamespace()
        manager.chats[1] = DownloadMessage(obj=old, prev="", torrent_ids=set())
        await manager.notify(1, '{"hashString": "h1"}')
        assert instance.bot.unpinned == [old]
        assert instance.bot.deleted == [old]


class TestTorrentStats:
    async def test_exception_marks_failure(self):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent()
        manager.client.get_torrent = AsyncMock(side_effect=RuntimeError("rpc"))
        await manager.update_torrent_stats()
        assert manager.torrents["h1"].failures == 1

    async def test_not_found_marks_gone(self):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent()
        manager.client.get_torrent = AsyncMock(return_value="Torrent not found")
        await manager.update_torrent_stats()
        assert manager.torrents["h1"].gone

    async def test_other_error_string_marks_failure(self):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent()
        manager.client.get_torrent = AsyncMock(return_value="some RPC error")
        await manager.update_torrent_stats()
        assert manager.torrents["h1"].failures == 1

    async def test_finished_marks_done(self, monkeypatch):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent()
        manager.client.get_torrent = AsyncMock(return_value={"isFinished": True})
        monkeypatch.setattr(manager, "_spawn_refresh", MagicMock())
        await manager.update_torrent_stats()
        assert manager.torrents["h1"].done

    async def test_milestones_fire_once(self, monkeypatch):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent()
        spawn = MagicMock()
        monkeypatch.setattr(manager, "_spawn_refresh", spawn)
        manager.client.get_torrent = AsyncMock(
            return_value={"percentDone": 0.6, "totalSize": 100}
        )
        await manager.update_torrent_stats()
        assert spawn.call_count == 1
        assert manager.torrents["h1"].refreshed_start
        assert manager.torrents["h1"].refreshed_half
        await manager.update_torrent_stats()
        assert spawn.call_count == 1

    async def test_done_and_gone_torrents_skipped(self):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent(done=True)
        manager.torrents["h2"] = make_torrent(gone=True)
        await manager.update_torrent_stats()
        manager.client.get_torrent.assert_not_awaited()

    async def test_mark_failure_gives_up_after_three(self):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent()
        manager._mark_failure("h1", "e1")
        manager._mark_failure("h1", "e2")
        assert not manager.torrents["h1"].gone
        manager._mark_failure("h1", "e3")
        assert manager.torrents["h1"].gone


class TestRefresh:
    async def test_spawn_refresh_skips_in_flight(self, monkeypatch):
        manager, instance = make_download_manager()
        manager._refresh_task = SimpleNamespace(done=lambda: False)
        create = MagicMock()
        monkeypatch.setattr(torrents_mod, "create_task", create)
        manager._spawn_refresh("50%")
        create.assert_not_called()

    async def test_spawn_refresh_creates_task(self, monkeypatch):
        manager, instance = make_download_manager()
        created: list[Any] = []

        def fake_create_task(coro: Any) -> Any:
            created.append(coro)
            coro.close()
            return SimpleNamespace(done=lambda: True)

        monkeypatch.setattr(torrents_mod, "create_task", fake_create_task)
        manager._spawn_refresh("50%")
        assert created

    async def test_refresh_media_lib_disabled(self, monkeypatch):
        manager, instance = make_download_manager()
        monkeypatch.setattr(torrents_mod, "MEDIA_LIB_REFRESH", None)
        monkeypatch.setattr(torrents_mod, "sleep", AsyncMock())
        await manager.refresh_media_lib(2)
        assert not any(level == "info" for level, _ in instance.log.events)

    async def test_refresh_media_lib_posts_when_configured(self, monkeypatch):
        manager, instance = make_download_manager()
        posts: list[Any] = []

        class FakeClient:
            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *args: Any) -> None:
                return None

            async def post(self, url: str) -> None:
                posts.append(url)

        monkeypatch.setattr(torrents_mod, "MEDIA_LIB_REFRESH", "http://emby/refresh")
        monkeypatch.setattr(torrents_mod, "AsyncClient", lambda: FakeClient())
        monkeypatch.setattr(torrents_mod, "sleep", AsyncMock())
        await manager.refresh_media_lib(2)
        assert posts == ["http://emby/refresh"]


class TestDownloadChats:
    def seeded(self) -> tuple[DownloadManager, FakeInstance]:
        manager, instance = make_download_manager()
        manager.chats[1] = DownloadMessage(obj=None, prev="", torrent_ids={"h1"})
        manager.torrents["h1"] = make_torrent(
            stats={"percentDone": 0.3, "rateDownload": 10, "totalSize": 100}
        )
        return manager, instance

    async def test_active_torrent_sends_and_pins(self, monkeypatch):
        manager, instance = self.seeded()
        monkeypatch.setattr(manager, "_spawn_refresh", MagicMock())
        await manager.update_chats()
        assert instance.bot.sent
        assert instance.bot.pinned

    async def test_completed_torrent_removed_and_refreshed(self, monkeypatch):
        manager, instance = self.seeded()
        manager.torrents["h1"].done = True
        spawn = MagicMock()
        monkeypatch.setattr(manager, "_spawn_refresh", spawn)
        await manager.update_chats()
        assert any("✅ Release" in text for _, text in instance.bot.sent)
        manager.client.remove_torrent.assert_awaited_once()
        assert "h1" not in manager.torrents
        spawn.assert_called_once_with("completion")

    async def test_gone_nearly_done_counts_as_completed(self, monkeypatch):
        manager, instance = self.seeded()
        manager.torrents["h1"].gone = True
        manager.torrents["h1"].stats = {"percentDone": 0.99}
        monkeypatch.setattr(manager, "_spawn_refresh", MagicMock())
        await manager.update_chats()
        assert any("✅ Release" in text for _, text in instance.bot.sent)
        # Gone torrents are not removed via RPC again.
        manager.client.remove_torrent.assert_not_awaited()

    async def test_gone_early_is_reported_as_lost(self, monkeypatch):
        manager, instance = self.seeded()
        manager.torrents["h1"].gone = True
        monkeypatch.setattr(manager, "_spawn_refresh", MagicMock())
        await manager.update_chats()
        assert any("canceled or removed" in text for _, text in instance.bot.sent)

    async def test_edit_failure_resends(self, monkeypatch):
        manager, instance = self.seeded()
        manager.chats[1].obj = SimpleNamespace()
        manager.chats[1].prev = "old"
        instance.bot.edit = AsyncMock(side_effect=RuntimeError("gone"))
        monkeypatch.setattr(manager, "_spawn_refresh", MagicMock())
        await manager.update_chats()
        assert instance.bot.sent

    async def test_unreferenced_torrent_dropped(self, monkeypatch):
        manager, instance = make_download_manager()
        manager.chats[1] = DownloadMessage(
            obj=SimpleNamespace(), prev="", torrent_ids={"h1"}
        )
        manager.torrents["h1"] = make_torrent(done=True)
        monkeypatch.setattr(manager, "_spawn_refresh", MagicMock())
        await manager.update_chats()
        assert "h1" not in manager.torrents
        assert 1 not in manager.chats
        assert instance.bot.unpinned
        assert instance.bot.deleted

    async def test_drop_keeps_torrent_referenced_elsewhere(self, monkeypatch):
        manager, instance = make_download_manager()
        manager.torrents["h1"] = make_torrent(done=True)
        manager.chats[1] = DownloadMessage(obj=None, prev="", torrent_ids={"h1"})
        manager.chats[2] = DownloadMessage(obj=None, prev="", torrent_ids={"h1"})
        spawn = MagicMock()
        monkeypatch.setattr(manager, "_spawn_refresh", spawn)
        message = manager.chats[1]
        manager._drop(message, "h1")
        assert "h1" in manager.torrents
        manager._drop(manager.chats[2], "h1")
        assert "h1" not in manager.torrents


class TestDownloadFormatting:
    def make_manager(self) -> DownloadManager:
        manager, _ = make_download_manager()
        return manager

    def test_create_message_orders_downloading_first_and_hides_extra(self):
        manager = self.make_manager()
        idle = make_torrent(name="Idle", stats={"rateDownload": 0, "totalSize": 10})
        active = make_torrent(
            name="Active",
            stats={"rateDownload": 100, "totalSize": 10, "eta": "1m"},
        )
        extra = [make_torrent(name=f"x{i}", stats={}) for i in range(3)]
        out = manager.create_message([idle, active, *extra])
        assert out.index("Active") < out.index("Idle")
        assert "+2 more in queue..." in out

    def test_create_message_eta_fallback(self):
        manager = self.make_manager()
        out = manager.create_message([make_torrent(stats={})])
        assert "♾" in out

    def test_short_name_truncates(self):
        manager = self.make_manager()
        assert manager._short_name("short") == "short"
        long_name = manager._short_name("x" * 100)
        assert len(long_name) == 44
        assert long_name.endswith("…")

    def test_format_speed_units(self):
        manager = self.make_manager()
        assert manager._format_speed(10) == "10B/s"
        assert manager._format_speed(2048) == "2.0KB/s"
        assert manager._format_speed(3 * 1024 * 1024) == "3.0MB/s"
        assert manager._format_speed(2 * 1024**3) == "2.0GB/s"
        assert manager._format_speed("bad") == "0B/s"

    async def test_start_loop_updates_then_sleeps(self, monkeypatch):
        manager, instance = make_download_manager()
        updates = AsyncMock()
        chats = AsyncMock()
        monkeypatch.setattr(manager, "update_torrent_stats", updates)
        monkeypatch.setattr(manager, "update_chats", chats)

        async def fake_sleep(_delay: float) -> None:
            raise _Stop

        monkeypatch.setattr(torrents_mod, "sleep", fake_sleep)
        with pytest.raises(_Stop):
            await manager.start()
        updates.assert_awaited_once()
        chats.assert_awaited_once()
