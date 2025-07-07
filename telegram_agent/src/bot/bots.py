from os import getenv

from dotenv import load_dotenv

from .abstract import AgenticBot
from .handlers import telegram_chat
from .instances import TelegramBot
from .logging import TelegramLogger
from .managers import DownloadManager

load_dotenv()


class AgenticTelegramBot(AgenticBot):
    def __init__(  # type: ignore
        self,
        telegram_id: str,
        dev: bool = False,
        managers: dict[str, type] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(dev, managers)
        self.log = TelegramLogger()
        self.bot = TelegramBot(telegram_id, **kwargs)


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

    managers: dict[str, type] = {}
    if getenv("RQBIT_URL"):
        managers["download_torrent"] = DownloadManager
    with AgenticTelegramBot(telegram_id, dev, managers) as bot:
        await bot.run(chat=telegram_chat)
