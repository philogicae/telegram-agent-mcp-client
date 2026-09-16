"""Tests for ``telegram_agent/src/core/stats.py``."""

import json
from json import dumps
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from telegram_agent.src.core import stats
from telegram_agent.src.core.stats import UserStats, flush_stats, register_interaction


def make_chat(chat_id: int = 1, **extra: Any) -> Any:
    values: dict[str, Any] = {"id": chat_id, "type": "private", "title": None}
    values.update(extra)
    return SimpleNamespace(**values)


def make_user(user_id: int = 7, **extra: Any) -> Any:
    values: dict[str, Any] = {
        "id": user_id,
        "username": None,
        "first_name": "Ada",
        "last_name": None,
        "phone_number": None,
        "language_code": "fr",
        "is_bot": False,
    }
    values.update(extra)
    return SimpleNamespace(**values)


def make_msg(
    chat_id: int = 1, message_id: int = 1, user: Any = None, chat: Any = None
) -> Any:
    return SimpleNamespace(
        chat=chat if chat is not None else make_chat(chat_id),
        message_id=message_id,
        from_user=make_user() if user is None else user,
    )


@pytest.fixture
def stats_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(stats, "_registry", None)
    return tmp_path / "stats"


class TestLoad:
    def test_missing_file_starts_empty(self, stats_dir):
        assert UserStats().data == {}

    def test_bot_keyed_layout_kept(self, stats_dir):
        stats_dir.mkdir(parents=True)
        payload = {"botA": {"1": {"first_seen": "x"}}}
        (stats_dir / "users.json").write_text(dumps(payload))
        assert UserStats().data == payload

    def test_flat_layout_nested_under_legacy(self, stats_dir):
        stats_dir.mkdir(parents=True)
        (stats_dir / "users.json").write_text(dumps({"1": {"first_seen": "x"}}))
        assert UserStats().data == {"legacy": {"1": {"first_seen": "x"}}}

    def test_empty_dict_nested_under_legacy(self, stats_dir):
        stats_dir.mkdir(parents=True)
        (stats_dir / "users.json").write_text("{}")
        assert UserStats().data == {"legacy": {}}

    def test_list_layout_migrated(self, stats_dir):
        stats_dir.mkdir(parents=True)
        (stats_dir / "users.json").write_text(dumps([{"first_seen": "x"}]))
        assert UserStats().data == {"legacy": {"0": {"first_seen": "x"}}}

    def test_non_dict_json_ignored(self, stats_dir):
        stats_dir.mkdir(parents=True)
        (stats_dir / "users.json").write_text("5")
        assert UserStats().data == {}

    def test_corrupt_file_quarantined(self, stats_dir):
        stats_dir.mkdir(parents=True)
        (stats_dir / "users.json").write_text("{not json")
        loaded = UserStats()
        assert loaded.data == {}
        assert (stats_dir / "users.corrupt").exists()
        assert not (stats_dir / "users.json").exists()


class TestRecord:
    def test_updates_chat_and_member_profiles(self, stats_dir):
        registry = UserStats()
        registry.record(make_msg(chat_id=10, user=make_user(7)))
        entry = registry.data["legacy"]["10"]
        assert entry["messages"] == 1
        assert entry["type"] == "private"
        profile = entry["users"]["7"]
        assert profile["first_name"] == "Ada"
        assert profile["full_name"] == "Ada"
        assert profile["is_bot"] is False
        assert "premium" not in profile  # Telegram did not expose the flag

    def test_premium_and_full_name_and_phone(self, stats_dir):
        registry = UserStats()
        user = make_user(7, first_name="Ada", last_name="Lovelace", premium=False)
        user.phone_number = "+33"
        registry.record(make_msg(user=user))
        profile = registry.data["legacy"]["1"]["users"]["7"]
        assert profile["full_name"] == "Ada Lovelace"
        assert profile["premium"] is False
        assert profile["phone_number"] == "+33"

    def test_duplicate_message_ignored(self, stats_dir):
        registry = UserStats()
        registry.record(make_msg(message_id=5))
        registry.record(make_msg(message_id=5))
        assert registry.data["legacy"]["1"]["messages"] == 1

    def test_seen_cap_evicts_oldest(self, stats_dir, monkeypatch):
        monkeypatch.setattr(stats, "_MAX_SEEN", 2)
        registry = UserStats()
        for message_id in range(1, 4):
            registry.record(make_msg(message_id=message_id))
        assert len(registry._seen) == 2
        assert list(registry._seen) == [(1, 2), (1, 3)]

    def test_bot_bucketing(self, stats_dir):
        registry = UserStats()
        registry.record(make_msg(), bot="botA")
        registry.record(make_msg(message_id=2))
        assert set(registry.data) == {"botA", "legacy"}

    def test_message_without_chat_ignored(self, stats_dir):
        registry = UserStats()
        registry.record(SimpleNamespace(chat=None))
        assert registry.data == {}

    def test_chat_without_id_ignored(self, stats_dir):
        registry = UserStats()
        registry.record(SimpleNamespace(chat=SimpleNamespace(id=None), message_id=1))
        assert registry.data == {}

    def test_recording_error_swallowed(self, stats_dir):
        registry = UserStats()
        # A chat id that cannot be coerced raises inside the guarded block.
        registry.record(
            SimpleNamespace(chat=SimpleNamespace(id="not-a-number"), message_id=1)
        )
        assert registry.data == {}

    def test_group_chat_fields(self, stats_dir):
        registry = UserStats()
        registry.record(make_msg(chat=make_chat(1, type="supergroup", title="Team")))
        entry = registry.data["legacy"]["1"]
        assert entry["type"] == "supergroup"
        assert entry["title"] == "Team"


class TestSave:
    def test_clean_registry_not_written(self, stats_dir):
        UserStats().save()
        assert not (stats_dir / "users.json").exists()

    def test_dirty_registry_persisted_atomically(self, stats_dir):
        registry = UserStats()
        registry.record(make_msg())
        registry.save()
        payload = json.loads((stats_dir / "users.json").read_text())
        assert payload["legacy"]["1"]["messages"] == 1
        assert not (stats_dir / "users.tmp").exists()

    async def test_delayed_flush_saves(self, stats_dir, monkeypatch):
        registry = UserStats()
        monkeypatch.setattr(stats, "sleep", AsyncMock())
        registry._dirty = True
        await registry._delayed_flush()
        assert (stats_dir / "users.json").exists()

    async def test_schedule_flush_creates_single_task(self, stats_dir):
        registry = UserStats()
        registry._dirty = True
        registry._schedule_flush()
        first = registry._flush_task
        registry._schedule_flush()
        assert registry._flush_task is first
        first.cancel()


class TestRegistry:
    def test_register_interaction_creates_registry(self, stats_dir):
        register_interaction(make_msg(), bot="botA")
        assert stats._registry is not None
        assert stats._registry.data["botA"]["1"]["messages"] == 1

    def test_flush_stats_no_registry_is_noop(self, stats_dir):
        flush_stats()

    def test_flush_stats_persists(self, stats_dir):
        register_interaction(make_msg())
        stats._registry._dirty = True
        flush_stats()
        assert (stats_dir / "users.json").exists()
