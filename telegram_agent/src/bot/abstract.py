from abc import ABC, abstractmethod
from functools import partial, wraps
from logging import INFO, basicConfig, getLogger
from typing import Any, Awaitable, Callable

from rich.logging import RichHandler

from .utils import Timer


class Logger(ABC):
    instance: str = ""
    level: Any = INFO

    def __init__(self) -> None:
        basicConfig(
            format="%(message)s",
            datefmt="[%d-%m %X]",
            level=self.level,
            handlers=[RichHandler()],
        )
        self.logger = getLogger("rich")

    def info(self, log: str) -> None:
        self.logger.info(log)

    def warn(self, log: str) -> None:
        self.logger.warning(f"WARN: {log}")

    def error(self, err: Exception) -> None:
        self.logger.error(f"ERROR: {err}")

    def debug(self, log: str) -> None:
        self.logger.debug(f"DEBUG: {log}")

    @abstractmethod
    def received(self, msg: Any) -> Timer:
        return Timer()

    @abstractmethod
    def sent(self, msg: Any, timer: Timer) -> None:
        pass


class Bot(ABC):
    @abstractmethod
    async def initialize(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        pass

    @abstractmethod
    async def start(self) -> None:
        pass


class AgenticBot(ABC):
    log: Logger
    bot: Any
    agent: Any

    def prepare_handlers(
        self, **kwargs: Callable[..., Awaitable[Any]]
    ) -> dict[str, Callable[..., Awaitable[Any]]]:
        return {k: partial(v, self) for k, v in kwargs.items()}

    @abstractmethod
    async def run(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        pass


def handler(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(agentic_bot: AgenticBot, *args, **kwargs) -> Any:  # type: ignore
        return await func(agentic_bot, *args, **kwargs)

    return wrapper
