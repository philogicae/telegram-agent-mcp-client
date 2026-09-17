"""Telegram Agent MCP Client package."""

# Must run before `.src`: its import chain reaches `langchain.mcp`, whose beta
# warning would otherwise fire before `patch_warnings` can filter it.
from .patch_warnings import _PATCH_ANCHOR

_PATCH_ANCHOR  # noqa: B018

from .src import (
    Agent,
    AgenticBot,
    AgenticTelegramBot,
    Bot,
    Logger,
    Manager,
    TelegramBot,
    TelegramLogger,
    handler,
    print_agents,
    print_tools,
    run_agent,
    run_telegram_bot,
    telegram_chat,
    telegram_report_issue,
)

__all__ = [
    "Agent",
    "AgenticBot",
    "AgenticTelegramBot",
    "Bot",
    "Logger",
    "Manager",
    "TelegramBot",
    "TelegramLogger",
    "handler",
    "print_agents",
    "print_tools",
    "run_agent",
    "run_telegram_bot",
    "telegram_chat",
    "telegram_report_issue",
]
