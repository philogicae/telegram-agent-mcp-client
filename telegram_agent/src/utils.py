from threading import Lock
from time import time
from typing import Any


class Singleton:
    _instance: Any
    _lock = Lock()

    def __new__(cls, *args, **kwargs) -> Any:  # type: ignore
        with cls._lock:
            if not hasattr(cls, "_instance"):
                cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance


class Timer:
    def __init__(self) -> None:
        self.start = time()

    def done(self) -> str:
        return f"{time() - self.start:.2f}s"
