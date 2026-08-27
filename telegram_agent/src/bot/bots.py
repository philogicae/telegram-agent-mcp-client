"""Bot implementations for Telegram Agent MCP Client."""

from asyncio import gather
from os import getenv
from typing import Any

from dotenv import load_dotenv

from .abstract import AgenticBot
from .handlers import telegram_chat, telegram_file, telegram_image, telegram_voice
from .instances import TelegramBot
from .logging import TelegramLogger
from .managers import DocumentManager, DownloadManager
from .relay import serve, start_relay

load_dotenv()


class AgenticTelegramBot(AgenticBot):
    """Agentic Telegram bot with managers."""

    def __init__(
        self,
        telegram_id: str,
        dev: bool = False,
        managers: dict[str, type] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(dev, managers)
        self.log = TelegramLogger()
        self.bot = TelegramBot(telegram_id, **kwargs)


async def run_telegram_bot(dev: bool = False) -> None:
    """Run the Telegram bot with the configured managers and handlers."""
    telegram_id: str | None = getenv("TELEGRAM_BOT_TOKEN")
    telegram_id_dev: str | None = getenv("TELEGRAM_BOT_TOKEN_DEV")
    if dev:
        if telegram_id_dev:
            telegram_id = telegram_id_dev
        else:
            raise ValueError("TELEGRAM_BOT_TOKEN_DEV is not set")
    elif not telegram_id:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    managers: dict[str, type] = {}
    handlers: dict[str, Any] = {
        "chat": telegram_chat,
    }
    if getenv("TRANSMISSION_URL"):
        managers["download_torrent"] = DownloadManager
    if getenv("RAG_URL"):
        managers["document"] = DocumentManager
        handlers["document"] = telegram_file
    if getenv("GEMINI_API_KEY"):
        handlers["voice"] = telegram_voice
        handlers["image"] = telegram_image

    with AgenticTelegramBot(telegram_id, dev, managers) as bot:
        relay = start_relay(bot)
        await gather(bot.run(**handlers), *([serve(relay)] if relay else []))
