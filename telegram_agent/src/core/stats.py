"""Persistent stats for every user/group interacting with each bot instance.

Each incoming Telegram message is recorded into ``{DATA_DIR}/stats/users.json``
(default ``./data/stats/users.json``), keyed by bot id then chat id:
``{<bot_id>: {<chat_id>: {first/last seen, type, title/handle,
per-member profiles (handle, names, phone number when Telegram exposes it,
language, bot/premium flags), counters}}}``.
Writes are debounced and atomic: bursts of messages coalesce into a single
save, so heavy traffic costs one small write every few seconds at most.
"""

import logging
from asyncio import get_running_loop, sleep
from collections import OrderedDict
from datetime import UTC, datetime
from json import JSONDecodeError, dump, load
from os import getenv
from pathlib import Path

log = logging.getLogger(__name__)

_FLUSH_DELAY = 5.0  # seconds; coalescing window for bursty chats
_MAX_SEEN = 4096  # dedup cap; enough for the longest handler-chain bursts
_LEGACY = "legacy"  # bucket for pre-nesting users.json content


def _now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class UserStats:
    """Registry backing users.json. Never raises to the caller."""

    def __init__(self) -> None:
        stats_dir = Path(getenv("DATA_DIR") or "./data") / "stats"
        self.path = stats_dir / "users.json"
        self.data: dict[str, dict] = {}
        self._dirty = False
        self._flush_task = None  # type: ignore[var-annotated]
        # Ordered set of (chat_id, message_id): voice/image handlers chain
        # into telegram_chat, so one message can hit the registry twice.
        self._seen: OrderedDict[tuple[int, int], None] = OrderedDict()
        self._load()

    def _load(self) -> None:
        """Load users.json, migrating older layouts into the bot-keyed form.

        Handles three generations of the file: list-of-chats, flat chat-id
        dict (nested under ``_LEGACY``) and the current bot-id keyed dict.
        A corrupt file is quarantined as ``.corrupt`` instead of crashing.
        """
        try:
            with self.path.open(encoding="utf-8") as f:
                raw: dict | list = load(f)
            if isinstance(raw, list):  # Very old format: list of chats.
                raw = {str(i): v for i, v in enumerate(raw)}
                log.warning("Migrated legacy list-based %s", self.path)
        except FileNotFoundError:
            return
        except JSONDecodeError, OSError, TypeError:
            # Corrupt or unreadable file: keep it aside for forensics,
            # start from scratch rather than crash the bot.
            backup = self.path.with_suffix(".corrupt")
            self.path.replace(backup)
            log.warning("Corrupt %s moved to %s", self.path, backup)
            return
        if not isinstance(raw, dict):
            return
        # Pre-bot-nesting format: top level maps chat ids -> entries carrying
        # activity fields. Nest them all under _LEGACY instead of dropping.
        if not raw or any(
            isinstance(v, dict) and "first_seen" in v for v in raw.values()
        ):
            raw = {_LEGACY: raw}
            log.warning("Migrated flat %s into '%s' bucket", self.path, _LEGACY)
        self.data = raw

    def record(self, message, bot: str | None = None) -> None:
        """Update the registry with one interaction; schedules a flush."""
        chat = getattr(message, "chat", None)
        if chat is None or getattr(chat, "id", None) is None:
            return
        try:
            key = (int(chat.id), int(getattr(message, "message_id", 0)))
            if key in self._seen:
                return
            self._seen[key] = None
            while (
                len(self._seen) > _MAX_SEEN
            ):  # ponytail: FIFO cap; bump if >4k in-flight
                self._seen.popitem(last=False)
            self._record(chat, getattr(message, "from_user", None), str(bot or _LEGACY))
        except Exception:
            log.exception("Failed to record interaction stats")
        else:
            self._schedule_flush()

    def _record(self, chat, user, bot: str) -> None:
        """Merge one interaction into ``self.data[bot][chat.id]``.

        Chat-level counters/fields are always updated; when Telegram
        exposes the sender, its member profile is refreshed with all
        available identity fields.
        """
        now = _now()
        entry = self.data.setdefault(bot, {}).setdefault(str(chat.id), {})
        entry.setdefault("first_seen", now)
        entry["last_seen"] = now
        entry["messages"] = entry.get("messages", 0) + 1
        entry["type"] = getattr(chat, "type", None)
        entry["title"] = getattr(chat, "title", None)
        entry["username"] = getattr(chat, "username", None)

        if user is not None and getattr(user, "id", None) is not None:
            members: dict[str, dict] = entry.setdefault("users", {})
            profile = members.setdefault(str(user.id), {})
            profile.setdefault("first_seen", now)
            profile["last_seen"] = now
            profile["messages"] = profile.get("messages", 0) + 1
            profile["username"] = getattr(user, "username", None)
            profile["first_name"] = getattr(user, "first_name", None)
            profile["last_name"] = getattr(user, "last_name", None)
            full_name = " ".join(
                filter(
                    None,
                    (
                        getattr(user, "first_name", None),
                        getattr(user, "last_name", None),
                    ),
                )
            )
            profile["full_name"] = full_name or None
            # Only present when Telegram privacy rules allow it.
            profile["phone_number"] = getattr(user, "phone_number", None)
            profile["language_code"] = getattr(user, "language_code", None)
            profile["is_bot"] = bool(getattr(user, "is_bot", False))
            premium = getattr(user, "premium", None)
            if premium is not None:
                profile["premium"] = bool(premium)

        self._dirty = True

    def _schedule_flush(self) -> None:
        """Debounce the next save: coalesce bursts into one delayed flush."""
        task = self._flush_task
        if task is not None and not task.done():
            return  # A pending flush already covers these changes.
        try:
            self._flush_task = get_running_loop().create_task(self._delayed_flush())
        except RuntimeError:  # No loop (CLI/tests): save synchronously.
            self.save()

    async def _delayed_flush(self) -> None:
        """Deferred save executed after ``_FLUSH_DELAY`` seconds."""
        await sleep(_FLUSH_DELAY)
        self.save()

    def save(self) -> None:
        """Atomically persist pending changes."""
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            dump(self.data, f, indent=2, sort_keys=True, ensure_ascii=False)
        tmp.replace(self.path)
        self._dirty = False


_registry: UserStats | None = None


def register_interaction(message, bot: str | None = None) -> None:
    """Record a TelegramMessage into the user-stats registry.

    ``bot`` identifies which bot instance received it (its Telegram id).
    Fire-and-forget: a missing/broken registry must never break the bot.
    """
    global _registry
    if _registry is None:
        _registry = UserStats()
    _registry.record(message, bot)


def flush_stats() -> None:
    """Best-effort synchronous flush (useful on shutdown)."""
    global _registry
    if _registry is not None:
        _registry.save()
