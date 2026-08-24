"""Core module for Telegram Agent MCP Client."""

from logging import WARNING, getLogger

from .agent import Agent, run_agent
from .config import print_agents
from .tools import print_tools

for lib in ["google_genai.models", "httpx"]:
    getLogger(lib).setLevel(WARNING)

__all__ = ["Agent", "print_agents", "print_tools", "run_agent"]
