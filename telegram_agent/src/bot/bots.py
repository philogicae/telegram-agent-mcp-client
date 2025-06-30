from os import getenv
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv

from ..core import Agent
from .abstract import AgenticBot
from .handlers import telegram_chat
from .instances import TelegramBot
from .logging import TelegramLogger

load_dotenv()


class AgenticTelegramBot(AgenticBot):
    def __init__(self, telegram_id: str, **kwargs) -> None:  # type: ignore
        self.log = TelegramLogger()
        self.bot = TelegramBot(telegram_id, **kwargs)
        self.agent = Agent()

    async def run(self, **kwargs: Callable[..., Awaitable[Any]]) -> None:
        try:
            await self.bot.initialize(**self.prepare_handlers(**kwargs))
            self.log.info("TelegramBot is ready!")
            await self.bot.start()
        except KeyboardInterrupt:
            self.log.info("Killed by KeyboardInterrupt")
        except Exception as e:
            self.log.error(e)


async def run_telegram_bot(dev: bool = False) -> None:
    telegram_id: str | None = getenv("TELEGRAM_BOT_ID")
    telegram_id_dev: str | None = getenv("TELEGRAM_BOT_ID_DEV")
    if dev:
        if telegram_id_dev:
            telegram_id = telegram_id_dev
        else:
            raise ValueError("TELEGRAM_BOT_ID_DEV is not set")
    else:
        if not telegram_id:
            raise ValueError("TELEGRAM_BOT_ID is not set")

    bot = AgenticTelegramBot(
        str(telegram_id),
        delay=0.2,
        group_msg_trigger="!",
        waiting="💭 I'm thinking...",
    )
    await bot.run(chat=telegram_chat)
