"""Utility classes for Telegram Agent MCP Client."""

import re
from threading import Lock
from time import time
from typing import Any

THINKING_RE = re.compile(r"<think(?:ing)?>(.*?)(?:</think(?:ing)?>|\Z)", re.DOTALL)


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


def extract_response(msg: Any) -> tuple[str, str | None]:
    """Extract (text, reasoning) from an LLM response message.

    Handles string content, content-block lists ("text"/"thinking" keys),
    DeepSeek-style reasoning_content kwargs and inline <think> tags.
    """
    reasoning: str | None = None
    if isinstance(ak := getattr(msg, "additional_kwargs", None), dict):
        for key in ("reasoning_content", "reasoning", "thinking"):
            if raw := ak.get(key):
                reasoning = str(raw).strip() or None
                break
    content = getattr(msg, "content", msg)
    items: list[Any] = (
        [content]
        if isinstance(content, str)
        else content
        if isinstance(content, list)
        else []
    )
    texts: list[str] = []
    for item in items:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            if item.get("thinking"):  # Anthropic-style thinking block
                reasoning = reasoning or str(item["thinking"]).strip()
            elif item.get("text"):
                texts.append(str(item["text"]))
    text = "\n".join(part.strip() for part in texts if part.strip())
    if matches := THINKING_RE.findall(text):  # Inline <think> tags (e.g. R1 models)
        reasoning = reasoning or next((m for m in reversed(matches) if m.strip()), None)
        text = THINKING_RE.sub("", text).strip()
    return text, reasoning
