"""Abstract base classes for bot architecture."""

from abc import ABC, abstractmethod
from asyncio import Event, Lock, gather, sleep
from collections.abc import Awaitable, Callable
from functools import partial, wraps
from logging import INFO, WARNING, basicConfig, getLogger
from logging import Logger as Logging
from time import monotonic
from typing import Any, Self

from rich.logging import RichHandler

from ..core import Agent
from ..utils import Timer

# Cap for Telegram 429 flood-wait retries (seconds). Telegram can request very
# large retry_after values; capping prevents the retry loop from blocking for
# the entire requested duration.
_FLOOD_WAIT_CAP = 60.0

# Network errors (DNS failures, connection resets, etc.) need longer backoff
# than the default 0.2s delay — retrying too fast just burns through the retry
# budget before DNS has a chance to recover. Use exponential backoff starting
# at 1s, capped at 10s.
_NETWORK_BACKOFF_BASE = 1.0
_NETWORK_BACKOFF_CAP = 10.0


class Logger(ABC):
    """Abstract base class for logging."""

    instance: str = "BOT"
    level: Any = INFO

    def __init__(self) -> None:
        basicConfig(
            format="%(message)s",
            datefmt="[%X]",
            level=self.level,
            handlers=[RichHandler(rich_tracebacks=True)],
        )
        parent_logger = __name__.rsplit(".", maxsplit=1)[0]
        for lib in Logging.manager.loggerDict:
            if not lib.startswith(parent_logger):
                getLogger(lib).setLevel(WARNING)
        self.logger = getLogger(self.instance)
        self.logger.setLevel(self.level)

    def info(self, log: str) -> None:
        self.logger.info(log)

    def warn(self, log: str) -> None:
        self.logger.warning(log)

    def warning(self, log: str) -> None:
        self.logger.warning(log)

    def error(self, err: Exception | str) -> None:
        self.logger.error(err)

    def exception(self, err: Exception | str) -> None:
        self.logger.exception(err)

    def debug(self, log: str) -> None:
        self.logger.debug(log)

    @abstractmethod
    def received(self, msg: Any) -> Timer:
        return Timer()

    @abstractmethod
    def sent(self, msg: Any, timer: Timer) -> None:
        pass


def fixed_default(_: Any, text: str, classic: bool = True) -> str:
    """Return text unchanged."""
    return text


def logify_default(
    _: Any, agent: str | None = "Logs", content: list[str] | str = ""
) -> str:
    """Format log message with agent name and content."""
    return f"{agent.replace(' ', '-') if agent else 'Logs'}:\n" + "\n".join(
        [content] if content and isinstance(content, str) else content
    )


class Bot(ABC):
    """Abstract base class for bot implementations."""

    core: Any
    delay: float = 0.2
    group_msg_trigger: str = "!"
    waiting: str = "💭 I'm thinking..."
    retries: int = 5
    fixed: Callable[..., str] = fixed_default
    logify: Callable[..., str] = logify_default

    def __init__(
        self,
        delay: float | None = None,
        group_msg_trigger: str | None = None,
        waiting: str | None = None,
        retries: int | None = None,
    ) -> None:
        if delay:
            self.delay = delay
        if group_msg_trigger:
            self.group_msg_trigger = group_msg_trigger
        if waiting:
            self.waiting = waiting
        if retries:
            self.retries = retries
        # Async rate limiter: enforces a minimum gap between consecutive
        # Telegram API calls across all chats, but yields to the event loop
        # while waiting so other handlers can run concurrently.
        self._api_lock: Lock = Lock()
        self._last_api_call: float = 0.0

    @abstractmethod
    async def initialize(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        pass

    @abstractmethod
    async def start(self) -> None:
        pass

    async def _throttle(self) -> None:
        """Wait if the last API call was too recent, then record the call.

        Uses an async lock so only one task checks/updates the timestamp at a
        time, but the wait is done with ``await sleep`` which yields to the
        event loop — other handlers keep running during the gap.
        """
        async with self._api_lock:
            now = monotonic()
            gap = now - self._last_api_call
            if gap < self.delay:
                await sleep(self.delay - gap)
            self._last_api_call = monotonic()

    async def _exec(
        self,
        method: Callable[..., Awaitable[Any]],
        *args: Any,
        retries: int | None = None,
        **kwargs: Any,
    ) -> Any:
        max_retries = self.retries if retries is None else retries
        retry = 0
        while True:
            await self._throttle()
            try:
                result: Any = await method(*args, **kwargs)
                return result
            except Exception as exc:
                # Abort immediately on "message to edit not found" —
                # retrying is pointless and wastes flood budget.
                exc_str = str(exc).lower()
                if "message to edit not found" in exc_str:
                    raise
                # Handle Telegram 429 flood-wait: respect retry_after
                # instead of blind retrying at the default delay. Cap the
                # wait so an absurd retry_after (e.g. 3600s) doesn't block
                # the retry loop indefinitely.
                retry_after = self._extract_retry_after(exc)
                if retry_after and retry_after > 0:
                    retry += 1
                    if retry > max_retries:
                        raise
                    wait = min(retry_after, _FLOOD_WAIT_CAP)
                    if wait < retry_after:
                        getLogger(__name__).warning(
                            "Telegram flood-wait retry_after=%.0fs capped to %.0fs",
                            retry_after,
                            wait,
                        )
                    await sleep(wait)
                    continue
                # Network errors (DNS failures, connection resets, etc.)
                # need exponential backoff — retrying at the default 0.2s
                # delay burns through the budget before DNS recovers.
                is_network = self._is_network_error(exc)
                retry += 1
                if retry > max_retries:
                    raise
                if is_network:
                    wait = min(
                        _NETWORK_BACKOFF_BASE * (2 ** (retry - 1)),
                        _NETWORK_BACKOFF_CAP,
                    )
                    getLogger(__name__).warning(
                        "Network error on %s (attempt %d/%d), retrying in %.1fs: %s",
                        getattr(method, "__name__", method),
                        retry,
                        max_retries,
                        wait,
                        exc,
                    )
                else:
                    wait = self.delay
                await sleep(wait)

    @staticmethod
    def _is_network_error(exc: Exception) -> bool:
        """Check if an exception is a network-level error needing backoff.

        Only connection-level errors (DNS failures, connection resets, etc.)
        qualify — HTTP error responses (400, 500) are NOT network errors and
        won't resolve with retries.
        """
        # telebot wraps aiohttp connection errors into RequestTimeout.
        # It only raises this for actual connection failures, not HTTP errors
        # (those become ApiTelegramException), so this is safe.
        exc_name = type(exc).__name__
        if exc_name == "RequestTimeout":
            return True
        # Direct aiohttp errors (used by _rich_request). Only treat
        # ClientConnectionError (DNS, reset, refused) as network errors —
        # ClientResponseError (HTTP 400/500) is a content/server error.
        try:
            import aiohttp

            if isinstance(exc, aiohttp.ClientConnectionError):
                return True
        except ImportError:
            pass
        return False

    @staticmethod
    def _extract_retry_after(exc: Exception) -> float | None:
        """Extract retry_after seconds from a Telegram 429 flood-wait exception."""
        # pytelegrambotapi stores the JSON payload on result_json
        result_json = getattr(exc, "result_json", None)
        if isinstance(result_json, dict):
            params = result_json.get("parameters")
            if isinstance(params, dict):
                retry_after = params.get("retry_after")
                if retry_after:
                    return float(retry_after)
        return None

    @abstractmethod
    async def send(self, *args: Any, **kwargs: Any) -> Any:
        pass

    @abstractmethod
    async def reply(self, *args: Any, **kwargs: Any) -> Any:
        pass

    @abstractmethod
    async def edit(self, *args: Any, **kwargs: Any) -> Any:
        pass

    @abstractmethod
    async def pin(self, *args: Any, **kwargs: Any) -> Any:
        pass

    @abstractmethod
    async def unpin(self, *args: Any, **kwargs: Any) -> Any:
        pass

    @abstractmethod
    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        pass


class Manager(ABC):
    """Abstract base class for managers."""

    name: str

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def notify(self, chat_id: int, data: Any) -> None:
        pass

    async def no_file(self, chat_id: int, filename: str, size: str) -> None:
        raise NotImplementedError

    async def file_too_large(self, chat_id: int, filename: str) -> None:
        raise NotImplementedError


class AgenticBot(ABC):
    """Abstract base class for agentic bots with managers."""

    dev: bool = False
    bot: Bot
    log: Logger
    agent: Any
    managers: dict[str, Manager]

    def __init__(
        self, dev: bool = False, managers: dict[str, type] | None = None
    ) -> None:
        self.dev = dev
        self.managers = {k: v(self) for k, v in managers.items()} if managers else {}
        self.pending_media: dict[int, list[tuple[bytes, str]]] = {}
        self.tts_enabled: dict[int, bool] = {}
        self.cancel_events: dict[int, Event] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        """Exit context manager - subclasses may override."""
        return

    def prepare_handlers(
        self, **kwargs: Callable[..., Awaitable[Any]]
    ) -> dict[str, Callable[..., Awaitable[Any]]]:
        return {k: partial(v, self) for k, v in kwargs.items()}

    async def run(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        try:
            self.agent = await Agent.init(self.dev)
            await self.bot.initialize(**self.prepare_handlers(**kwargs))
            self.log.info(f"{self.bot.__class__.__name__} is ready!")
            await gather(
                self.bot.start(),
                *(manager.start() for manager in self.managers.values()),
            )
        except KeyboardInterrupt:
            self.log.info(f"{self.bot.__class__.__name__} killed by KeyboardInterrupt")
        except Exception:
            self.log.exception("Error running bot")


def handler(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Decorator for handler functions."""

    @wraps(func)
    async def wrapper(instance: AgenticBot, *args: Any, **kwargs: Any) -> Any:
        return await func(instance, *args, **kwargs)

    return wrapper
