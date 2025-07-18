from abc import ABC, abstractmethod
from asyncio import gather, sleep
from functools import partial, wraps
from logging import INFO, basicConfig, getLogger
from time import time
from typing import Any, Awaitable, Callable

from rich.logging import RichHandler

from ..core import Agent
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
    last_call: float = 0
    delay: float = 0.2
    group_msg_trigger: str = "!"
    waiting: str = "💭  _I'm thinking_..."

    def __init__(
        self,
        delay: float | None = None,
        group_msg_trigger: str | None = None,
        waiting: str | None = None,
    ) -> None:
        if delay:
            self.delay = delay
        if group_msg_trigger:
            self.group_msg_trigger = group_msg_trigger
        if waiting:
            self.waiting = waiting

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
                except Exception as e:
                    retry += 1
                    if retry > 3:
                        raise e
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
    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def notify(self, chat_id: int, data: Any) -> None:
        pass


class AgenticBot(ABC):
    dev: bool = False
    bot: Any
    log: Logger
    agent: Any
    managers: dict[str, Manager]

    def __init__(
        self, dev: bool = False, managers: dict[str, type] | None = None
    ) -> None:
        self.dev = dev
        self.managers = {k: v(self) for k, v in managers.items()} if managers else {}

    def __enter__(self) -> "AgenticBot":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        pass

    def prepare_handlers(
        self, **kwargs: Callable[..., Awaitable[Any]]
    ) -> dict[str, Callable[..., Awaitable[Any]]]:
        return {k: partial(v, self) for k, v in kwargs.items()}

    async def run(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        try:
            self.agent = await Agent.init_with_tools(self.dev)
            await self.bot.initialize(**self.prepare_handlers(**kwargs))
            self.log.info(f"{self.bot.__class__.__name__} is ready!")
            await gather(
                self.bot.start(),
                *map(lambda manager: manager.start(), self.managers.values()),
            )
        except KeyboardInterrupt:
            self.log.info(f"{self.bot.__class__.__name__} killed by KeyboardInterrupt")
        except Exception as e:
            self.log.error(e)


def handler(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(instance: AgenticBot, *args, **kwargs) -> Any:  # type: ignore
        return await func(instance, *args, **kwargs)

    return wrapper
