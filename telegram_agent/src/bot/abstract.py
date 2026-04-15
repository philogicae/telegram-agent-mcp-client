"""Abstract base classes for bot architecture."""

from abc import ABC, abstractmethod
from asyncio import gather, sleep
from collections.abc import Awaitable, Callable
from functools import partial, wraps
from logging import INFO, WARNING, basicConfig, getLogger
from logging import Logger as Logging
from time import time
from typing import Any, Self

from rich.logging import RichHandler

from ..core import Agent
from ..utils import Timer


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


def fixed_default(_: Any, text: str) -> str:
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
    last_call: float = 0
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

    @abstractmethod
    async def initialize(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        pass

    @abstractmethod
    async def start(self) -> None:
        pass

    def _called(self) -> None:
        self.last_call = time()

    def _is_free(self) -> bool:
        return self.last_call + self.delay < time()

    async def _exec(
        self, method: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any:
        retry = 0
        while True:
            if self._is_free():
                try:
                    result: Any = await method(*args, **kwargs)
                    self._called()
                    return result
                except Exception:
                    retry += 1
                    if retry > self.retries:
                        raise
            else:
                await sleep(self.delay)

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
            self.agent = await Agent.init(self.dev, enable_graph=False)
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
