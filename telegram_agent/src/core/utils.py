from datetime import datetime, timezone
from enum import Enum
from os import makedirs
from re import sub
from time import time
from typing import Any

from aiosqlite import connect
from graphiti_core.edges import EntityEdge
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from pydantic import BaseModel


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


class Singleton:
    _instance: Any

    def __new__(cls, *args, **kwargs) -> Any:  # type: ignore
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance


class Timer:
    def __init__(self) -> None:
        self.start = time()

    def done(self) -> str:
        return f"{time() - self.start:.2f}s"


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


