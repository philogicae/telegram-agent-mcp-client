"""Utility classes for Telegram Agent MCP Client."""

from threading import Lock
from time import time
from typing import Any


class Singleton:
    """Singleton base class using thread-safe initialization."""

    _instance: Any
    _lock = Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        """Create or return the singleton instance."""
        with cls._lock:
            if not hasattr(cls, "_instance"):
                cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance


class Timer:
    """Simple timer for measuring elapsed time."""

    def __init__(self) -> None:
        """Initialize the timer."""
        self.start = time()

    def done(self) -> str:
        """Return the elapsed time as a formatted string."""
        return f"{time() - self.start:.2f}s"
