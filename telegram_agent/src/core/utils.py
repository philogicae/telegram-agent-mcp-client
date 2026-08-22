"""Core utilities for agent and memory management."""

from datetime import UTC, datetime
from enum import Enum
from json import dumps
from os import getenv
from pathlib import Path
from re import sub
from typing import Any, cast

from aiosqlite import connect
from graphiti_core.edges import EntityEdge
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    trim_messages,
)
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import StateSnapshot
from pydantic import BaseModel, Field, ValidationError

from ..utils import extract_response
from .llm import LLM, can_struct, mark_alive, mark_dead


class Flag(Enum):
    """Flags for detecting error states in tool results."""

    ERROR = "error:"
    _ERROR = " error"
    ERROR_ = "error "
    _FAILED = " failed"
    FAILED_ = "failed "


class Usage:
    """Track and accumulate LLM usage statistics."""

    def __init__(self) -> None:
        self.total: dict[str, Any] = {}

    def _add_usage(self, dict1: dict[str, Any], dict2: dict[str, Any]) -> None:
        for k, v in dict2.items():
            if isinstance(v, dict):
                if k not in dict1:
                    dict1[k] = {}
                self._add_usage(dict1[k], v)
            else:
                dict1[k] = dict1.get(k, 0) + v

    def add_usage(self, usage: dict[str, Any]) -> None:
        """Add usage stats to the total."""
        self._add_usage(self.total, usage)

    def __str__(self) -> str:
        return " | ".join([f"{k}: {v}" for k, v in self.total.items()])


def format_called_tool(tool: Any) -> str:
    """Format a tool name for display."""
    return sub("_|-", " ", str(tool)).title()


def checkpointer(dev: bool = False, persist: bool = False) -> BaseCheckpointSaver:
    """Create a checkpoint saver for the graph."""
    if dev or not persist:
        return InMemorySaver()
    data_folder = Path(getenv("DATA_DIR", "./data"))
    data_folder.mkdir(parents=True, exist_ok=True)
    return AsyncSqliteSaver(connect(str(data_folder / "checkpointer.sqlite")))


def pre_agent_hook(
    state: dict[str, Any] | Any, remove_all: bool = False, max_tokens: int = 50000
) -> dict[str, Any]:
    """Pre-process messages before agent execution."""
    messages: list[BaseMessage] = cast(
        "list[BaseMessage]",
        state.get("messages", []) if isinstance(state, dict) else [],
    )
    trimmed_messages = trim_messages(
        messages=messages,
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=max_tokens,
        start_on="human",
        allow_partial=True,
        # end_on=("human", "tool"),
    )
    if remove_all:
        return {"messages": [RemoveMessage(REMOVE_ALL_MESSAGES), *trimmed_messages]}
    return {"messages": trimmed_messages}


dt_min_aware = datetime.min.replace(tzinfo=UTC)
dt_max_aware = datetime.max.replace(tzinfo=UTC)


def sort_edges(edge: EntityEdge) -> tuple[datetime, datetime]:
    """Sort edges by start and end time."""
    start_time = edge.valid_at or edge.created_at
    end_time = edge.expired_at or edge.invalid_at
    return (
        start_time or dt_min_aware,
        end_time or dt_max_aware,
    )


def format_date(date: datetime) -> str:
    """Format a datetime for display, removing time and date when appropriate."""
    return (
        date.strftime("%Y-%m-%d %H:%M:%S")
        .replace(" 00:00:00", "")
        .replace("-01-01", "")
    )


class ReContext(BaseModel):
    """Model for recontextualized user messages."""

    summary: str = Field(description="Summary of the chat history")
    user_message: str = Field(description="Rephrased user message")


class FilteredMemories(BaseModel):
    """Model for filtered episodic memories."""

    memories: list[str] = Field(description="Filtered memories")


def append_structured_output(model: type[BaseModel]) -> str:
    """Append JSON output format instructions to a prompt for a given Pydantic model."""
    schema = model.model_json_schema()
    return f"\n\n# JSON Output Schema\n```json\n{dumps(schema)}\n```"


def parse_structured_output(raw: str | AIMessage, model: type[BaseModel]) -> BaseModel:
    """Parse a JSON string from an LLM output into the given Pydantic model."""
    text, _ = extract_response(raw)
    candidates: list[str] = []
    code_block = text.find("```")
    if code_block != -1:
        end = text.find("```", code_block + 3)
        if end != -1:
            fenced = text[code_block + 3 : end].strip()
            if fenced.lower().startswith("json"):
                fenced = fenced[4:].strip()
            candidates.append(fenced)
    brace_start, brace_end = text.find("{"), text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidates.append(text[brace_start : brace_end + 1])
    errors: list[ValidationError] = []
    for candidate in candidates or [""]:
        try:
            return model.model_validate_json(candidate)
        except ValidationError as e:
            errors.append(e)
    raise errors[0]


async def run_schema(
    messages: list[Any], schema: type[BaseModel], provider: str | None = None
) -> BaseModel:
    """Complete messages into `schema`, failing over across providers.

    Native structured output when the picked provider supports it; a JSON
    schema prompt + robust parse otherwise. Failures immediately fall back
    to the next candidate: each error counts a strike via mark_dead() and
    the retry re-picks, skipping cooled-down/jailed providers until every
    capable candidate was tried.
    """
    err: Exception | None = None
    tried: set[str] = set()
    while True:
        picked = provider or LLM.pick("structured", fast=True) or LLM.pick(fast=True)
        provider = None  # force a fresh pick on retry
        if not picked or picked in tried:
            break
        tried.add(picked)
        try:
            llm: Any = LLM.get(picked)
            if can_struct(picked):
                result = await llm.with_structured_output(schema=schema).ainvoke(
                    messages
                )
            else:
                first, rest = messages[0], messages[1:]
                if isinstance(first.content, str):
                    first = HumanMessage(
                        first.content + append_structured_output(schema)
                    )
                else:
                    rest, first = (
                        [first, *rest],
                        SystemMessage(append_structured_output(schema).strip()),
                    )
                result = parse_structured_output(
                    await llm.ainvoke([first, *rest]), schema
                )
            mark_alive(picked)
            return result
        except Exception as e:
            err = e
            mark_dead(picked)
    raise RuntimeError(f"No LLM provider available: {err}") from err


async def summarize_and_rephrase(
    state: StateSnapshot, user_msg: str, provider: str | None = None
) -> ReContext:
    """Summarize chat history and rephrase the user message."""
    chat_history: list[Any] = []
    if state.values.get("messages"):
        chat_history = pre_agent_hook(state.values).get("messages", [])
    chat_history.extend(
        [
            HumanMessage(
                """Analyze the chat history and the latest user message to provide:
1. An exhaustive compressed summary of the conversation so far (return 'None' if empty).
2. A rephrased version of the latest user message that incorporates context to make it self-contained.

# Instructions for Rephrasing
- Resolve ambiguous references (e.g., "it", "that", "the first one") based on history.
- Expand short responses (e.g., "yes", "no") to include the action being confirmed/rejected.
- Maintain the original `<user>: <message>` format.
- Correct typos but preserve the user's original intent.

# Example
History: Bob asked to find Dexter S01E01. Agent only found the complete season.
Input: 'Bob: Take it'
Rephrased: 'Bob: Download the complete season 1 of Dexter that you found'"""
            ),
            HumanMessage(f"# User Message\n{user_msg}"),
        ]
    )
    return cast("ReContext", await run_schema(chat_history, ReContext, provider))


async def filter_relevant_memories(
    memories: str, context: str, user_msg: str, provider: str | None = None
) -> str:
    """Filter episodic memories for relevance to the current context."""
    chat_history: list[Any] = [
        SystemMessage(
            f"""Analyze the provided episodic memories in relation to the current context and user message.
Identify and return ONLY the memories that are directly relevant to the user's current intent.

# Instructions
- Filter out irrelevant or out-of-context information.
- Return the relevant memory lines intact but compact.
- If no memories are relevant, return an empty list.

# Episodic Memories
{memories}

# Context
{context}"""
        ),
        HumanMessage(f"# User Message\n{user_msg}"),
    ]
    result = cast(
        "FilteredMemories",
        await run_schema(chat_history, FilteredMemories, provider),
    )
    return (
        "\n".join(result.memories)
        if hasattr(result, "memories")
        and result.memories
        and len(result.memories[0]) > 8
        else ""
    )
