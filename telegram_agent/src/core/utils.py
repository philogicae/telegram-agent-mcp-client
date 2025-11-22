from datetime import datetime, timezone
from enum import Enum
from os import makedirs
from re import sub
from typing import Any

from aiosqlite import connect
from graphiti_core.edges import EntityEdge
from langchain.messages import HumanMessage, RemoveMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import StateSnapshot
from pydantic import BaseModel, Field

from .llm import LLM


class Flag(Enum):
    ERROR = "error:"
    _ERROR = " error"
    ERROR_ = "error "
    _FAILED = " failed"
    FAILED_ = "failed "


class Usage:
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
        self._add_usage(self.total, usage)

    def __str__(self) -> str:
        return " | ".join([f"{k}: {v}" for k, v in self.total.items()])


def format_called_tool(tool: Any) -> str:
    return sub("_|-", " ", str(tool)).title()


def checkpointer(dev: bool = False, persist: bool = False) -> BaseCheckpointSaver:  # type: ignore
    if dev or not persist:
        return InMemorySaver()
    data_folder = "/app/data"
    makedirs(data_folder, exist_ok=True)
    return AsyncSqliteSaver(connect(f"{data_folder}/checkpointer.sqlite"))


def pre_model_hook(state: dict[str, Any], remove_all: bool = False) -> dict[str, Any]:
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=5000,
        start_on="human",
        allow_partial=True,
        # end_on=("human", "tool"),
    )
    if remove_all:
        return {"messages": [RemoveMessage(REMOVE_ALL_MESSAGES)] + trimmed_messages}
    return {"llm_input_messages": trimmed_messages}


dt_min_aware = datetime.min.replace(tzinfo=timezone.utc)
dt_max_aware = datetime.max.replace(tzinfo=timezone.utc)


def sort_edges(edge: EntityEdge) -> tuple[datetime, datetime]:
    start_time = edge.valid_at or edge.created_at
    end_time = edge.expired_at or edge.invalid_at
    return (
        start_time if start_time else dt_min_aware,
        end_time if end_time else dt_max_aware,
    )


def format_date(date: datetime) -> str:
    return (
        date.strftime("%Y-%m-%d %H:%M:%S")
        .replace(" 00:00:00", "")
        .replace("-01-01", "")
    )


class ReContext(BaseModel):
    summary: str = Field(description="Summary of the chat history")
    user_message: str = Field(description="Rephrased user message")


class FilteredMemories(BaseModel):
    memories: list[str] = Field(description="Filtered memories")


def summarize_and_rephrase(
    state: StateSnapshot, user_msg: str, provider: str = "gemini"
) -> ReContext:
    chat_history: list[Any] = []
    if state.values.get("messages"):
        chat_history = pre_model_hook(state.values).get("llm_input_messages", [])
    chat_history.append(
        HumanMessage(
            f"""Analyze the chat history and the latest user message to provide:
1. A compressed summary of the conversation so far (return 'None' if empty).
2. A rephrased version of the latest user message that incorporates context to make it self-contained.

# Instructions for Rephrasing
- Resolve ambiguous references (e.g., "it", "that", "the first one") based on history.
- Expand short responses (e.g., "yes", "no") to include the action being confirmed/rejected.
- Maintain the original `<user>: <message>` format.
- Correct typos but preserve the user's original intent.

# Example
History: Bob asked to find Dexter S01E01. Agent only found the complete season.
Input: "Bob: Take it"
Rephrased: "Bob: Download the complete season 1 of Dexter that you found"

# User Message
{user_msg}"""
        )
    )
    llm: Any = LLM.get(provider)
    structured_llm = llm.with_structured_output(schema=ReContext)
    result: ReContext = structured_llm.invoke(chat_history)
    return result


def filter_relevant_memories(
    memories: str, context: str, user_msg: str, provider: str = "gemini"
) -> str:
    llm: Any = LLM.get(provider)
    structured_llm = llm.with_structured_output(schema=FilteredMemories)
    result: FilteredMemories = structured_llm.invoke(
        [
            HumanMessage(
                f"""Analyze the provided episodic memories in relation to the current context and user message.
Identify and return ONLY the memories that are directly relevant to the user's current intent.

# Instructions
- Filter out irrelevant or out-of-context information.
- Return the relevant memory lines intact but compact.
- If no memories are relevant, return an empty list.

# Episodic Memories
{memories}

# Context
{context}

# User Message
{user_msg}"""
            )
        ]
    )
    return (
        "\n".join(result.memories)
        if hasattr(result, "memories")
        and result.memories
        and len(result.memories[0]) > 8
        else ""
    )
