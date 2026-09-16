"""Shared pytest fixtures and test-session isolation.

Import order matters: this module keeps the developer's real environment out
of the test session *before* any application module is imported:

- `.env` loading is disabled, so real tokens/URLs never leak into tests;
- ``CONFIG_DIR``/``DATA_DIR`` point at a throwaway directory, so tests never
  read the real config or write real state.

Individual tests override module-level paths (``TOOL_DIR``, ``CONFIG_DIR``…)
with ``monkeypatch.setattr`` on the module under test.
"""

import os
from pathlib import Path
from tempfile import mkdtemp

_SESSION_DIR = Path(mkdtemp(prefix="tam-tests-"))
os.environ["CONFIG_DIR"] = str(_SESSION_DIR / "config")
os.environ["DATA_DIR"] = str(_SESSION_DIR / "data")

import dotenv
import pytest


def _no_dotenv(*_args: object, **_kwargs: object) -> bool:
    """Keep tests off the real ``.env`` file."""
    return False


dotenv.load_dotenv = _no_dotenv


@pytest.fixture(autouse=True)
def _no_stats_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler tests must not touch the real stats registry/flush scheduling."""
    monkeypatch.setattr(
        "telegram_agent.src.bot.abstract.register_interaction",
        lambda *args, **kwargs: None,
    )
