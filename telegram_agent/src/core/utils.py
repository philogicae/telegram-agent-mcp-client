from enum import Enum
from re import sub
from time import time
from typing import Any


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
