"""Bot module for Telegram Agent MCP Client."""

from .abstract import AgenticBot, Bot, Logger, Manager, handler
from .bots import AgenticTelegramBot, run_telegram_bot
from .handlers import (
    telegram_chat,
    telegram_image,
    telegram_report_issue,
    telegram_voice,
)
from .instances import TelegramBot
from .logging import TelegramLogger
from .managers import DownloadManager

__all__ = [
    "AgenticBot",
    "AgenticTelegramBot",
    "Bot",
    "DownloadManager",
    "Logger",
    "Manager",
    "TelegramBot",
    "TelegramLogger",
    "handler",
    "run_telegram_bot",
    "telegram_chat",
    "telegram_image",
    "telegram_report_issue",
    "telegram_voice",
]
