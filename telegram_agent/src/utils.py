"""Utility classes for Telegram Agent MCP Client."""

import re
from hashlib import sha256
from json import JSONDecodeError, loads
from threading import Lock
from time import time
from typing import Any

THINKING_RE = re.compile(r"<think(?:ing)?>(.*?)(?:</think(?:ing)?>|\Z)", re.DOTALL)

# GLM-native tool-call markup: the opencode zen gateway occasionally returns
# GLM tool calls serialized as plain text (<tool_call>name<arg_key>k</arg_key>
# <arg_value>v</arg_value></tool_call>) instead of structured tool_calls.
# `key` ends at its own closing tag; `value` ends at its own closing tag (the
# format is ambiguous beyond that) and may span multiple lines (JSON filters).
_TOOL_CALL_BLOCK_RE = re.compile(
    r"<tool_call>\s*(?P<name>[^<\s>]+)\s*(?P<args>.*?)</tool_call>", re.DOTALL
)
_TOOL_CALL_ARG_RE = re.compile(
    r"<arg_key>(?P<key>[^<]+?)</arg_key><arg_value>(?P<value>.*?)</arg_value>",
    re.DOTALL,
)


def _to_hash(payload: str) -> str:
    """Hash a payload using SHA256 (first 16 hex chars)."""
    return sha256(payload.encode()).hexdigest()[:16]


def parse_tool_call_markup(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Split GLM-native tool-call markup out of a message text.

    Returns the remaining prose (markup spans removed, edges stripped) and the
    parsed calls as langchain ``ToolCall`` dicts (name/args/id/type). Args
    listed as JSON objects/arrays are deserialized; other values stay strings.
    """
    calls: list[dict[str, Any]] = []

    def _collect(match: re.Match) -> str:
        args: dict[str, Any] = {}
        for arg in _TOOL_CALL_ARG_RE.finditer(match.group("args")):
            key, value = arg.group("key"), arg.group("value")
            if value[:1] in "{[":
                try:
                    args[key] = loads(value)
                    continue
                except JSONDecodeError:
                    pass
            args[key] = value
        calls.append(
            {
                "name": match.group("name"),
                "args": args,
                "id": f"call_{_to_hash(f'{match.group("name")}:{match.start()}')}",
                "type": "tool_call",
            }
        )
        return ""

    prose = _TOOL_CALL_BLOCK_RE.sub(_collect, text or "").strip()
    return prose, calls


def is_tool_call_markup_only(text: str) -> bool:
    """Whether a message text is nothing but tool-call markup spans.

    Blank lines around and between spans are ignored; any real prose means
    the text is an answer that happens to contain markup, not markup-only.
    """
    return bool(text) and not parse_tool_call_markup(text)[0]


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
