"""Lightweight stand-ins for Telegram/agent objects, shared across tests."""

from typing import Any

from telebot.types import Message

from telegram_agent.src.utils import Timer


def make_message(
    text: str = "hello",
    *,
    chat_id: int = 123,
    user_id: int = 456,
    message_id: int = 1,
    chat_type: str = "private",
    from_user: bool = True,
    **extra: Any,
) -> Message:
    """Build a real ``telebot`` Message from a JSON payload."""
    payload: dict[str, Any] = {
        "message_id": message_id,
        "chat": {"id": chat_id, "type": chat_type},
        "date": 0,
        "text": text,
    }
    if from_user:
        payload["from"] = {"id": user_id, "is_bot": False, "first_name": "Tester"}
    payload.update(extra)
    return Message.de_json(payload)


class FakeLogger:
    """Records log calls; mirrors the application ``Logger`` interface."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def info(self, log: str) -> None:
        self.events.append(("info", str(log)))

    def warn(self, log: str) -> None:
        self.events.append(("warn", str(log)))

    def warning(self, log: str) -> None:
        self.events.append(("warn", str(log)))

    def error(self, err: Exception | str) -> None:
        self.events.append(("error", str(err)))

    def exception(self, err: Exception | str) -> None:
        self.events.append(("exception", str(err)))

    def debug(self, log: str) -> None:
        self.events.append(("debug", str(log)))

    def received(self, msg: Any) -> Timer:
        self.events.append(("received", str(getattr(msg, "text", ""))))
        return Timer()

    def sent(self, msg: Any, timer: Timer) -> None:
        self.events.append(("sent", "sent"))


class FakeCore:
    """Placeholder for ``AsyncTeleBot``; tests script its async methods."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    async def send_chat_action(self, *args: Any, **kwargs: Any) -> None:
        self._record("send_chat_action", *args, **kwargs)

    async def send_photo(self, *args: Any, **kwargs: Any) -> None:
        self._record("send_photo", *args, **kwargs)

    async def send_media_group(self, *args: Any, **kwargs: Any) -> None:
        self._record("send_media_group", *args, **kwargs)

    async def send_voice(self, *args: Any, **kwargs: Any) -> None:
        self._record("send_voice", *args, **kwargs)


class FakeBot:
    """Stands in for a ``Bot`` implementation, recording every output."""

    def __init__(self, waiting: str = "💭 I'm thinking...") -> None:
        self.sent: list[tuple[Any, Any]] = []
        self.replies: list[tuple[Any, Any]] = []
        self.edits: list[tuple[Any, Any, dict[str, Any]]] = []
        self.deleted: list[Any] = []
        self.pinned: list[Any] = []
        self.unpinned: list[Any] = []
        self.waiting = waiting
        self.edit_cache: dict[int, Any] = {}
        self.core = FakeCore()
        self.id = "1"
        self._next_id = 100

    @staticmethod
    def logify(agent: str | None = None, content: Any = "") -> str:
        logs = [content] if isinstance(content, str) else list(content or [])
        return f"{agent or 'Logs'}:\n" + "\n".join(str(c) for c in logs)

    async def send(self, message_or_chat_id: Any, text: str | None = None) -> Any:
        self.sent.append((message_or_chat_id, text))
        self._next_id += 1
        return make_message("sent", message_id=self._next_id)

    async def reply(self, to_message: Any, text: str | None = None) -> Any:
        self.replies.append((to_message, text))
        self._next_id += 1
        return make_message("reply", message_id=self._next_id)

    async def edit(self, message: Any, text: str, **kwargs: Any) -> bool:
        self.edits.append((message, text, kwargs))
        return True

    async def pin(self, message: Any) -> bool:
        self.pinned.append(message)
        return True

    async def unpin(self, message: Any) -> bool:
        self.unpinned.append(message)
        return True

    async def delete(self, message: Any) -> bool:
        self.deleted.append(message)
        return True


class FakeAgent:
    """Stands in for ``Agent``: allowlist checks and a scripted chat stream."""

    def __init__(
        self,
        *,
        allowed: dict[str, str] | None = None,
        admin: dict[str, str] | None = None,
        chat_events: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.user_config = {
            "admin": {"users": admin or {}},
            "allowed": {"users": allowed or {}},
        }
        self.chat_events = chat_events or []
        self.chat_calls: list[Any] = []

    def _group_users(self, group: str) -> dict[str, str]:
        cfg = self.user_config.get(group)
        return cfg.get("users", {}) if isinstance(cfg, dict) else {}

    def is_allowed(self, user_id: int | str) -> bool:
        return any(str(user_id) in self._group_users(g) for g in self.user_config)

    def is_admin(self, user_id: int | str) -> bool:
        return str(user_id) in self._group_users("admin")

    def add_allowed_user(self, user_id: int | str, name: str) -> None:
        self.user_config.setdefault("allowed", {}).setdefault("users", {})[
            str(user_id)
        ] = name

    def remove_allowed_user(self, user_id: int | str) -> bool:
        users = self._group_users("allowed")
        if str(user_id) not in users:
            return False
        del users[str(user_id)]
        return True

    async def chat(self, content: Any):
        """Yield the scripted events for this fake agent."""
        self.chat_calls.append(content)
        for event in self.chat_events:
            yield event


class FakeInstance:
    """Stands in for an ``AgenticBot`` instance in handler/manager tests."""

    def __init__(
        self,
        *,
        agent: Any = None,
        bot: Any = None,
        managers: dict[str, Any] | None = None,
    ) -> None:
        self.agent = agent if agent is not None else FakeAgent()
        self.bot = bot if bot is not None else FakeBot()
        self.log = FakeLogger()
        self.managers = managers or {}
        self.pending_media: dict[int, list[tuple[bytes, str]]] = {}
        self.tts_enabled: dict[int, bool] = {}
        self.cancel_events: dict[int, Any] = {}
        self.chat_queues: dict[int, Any] = {}
        self.chat_workers: dict[int, Any] = {}
