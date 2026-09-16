"""Tests for ``telegram_agent/__main__.py``."""

import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from telegram_agent import __main__ as main_mod


class TestPrintHelpers:
    def test_status_warning_error(self, capsys):
        main_mod.print_status("ok")
        main_mod.print_warning("careful")
        main_mod.print_error("bad")
        out = capsys.readouterr().out
        assert "\033[0;32mok" in out
        assert "\033[1;33mcareful" in out
        assert "\033[0;31mbad" in out


@pytest.fixture
def cli_spy(monkeypatch):
    """Replace every CLI target and the runner with spies."""
    calls: dict[str, Any] = {}

    def spy(name: str) -> Any:
        thing = MagicMock(return_value=object())
        monkeypatch.setattr(main_mod, name, thing)
        calls[name] = thing
        return thing

    for name in (
        "print_tools",
        "print_agents",
        "run_agent",
        "run_telegram_bot",
        "install_playwright",
    ):
        spy(name)
    monkeypatch.setattr(
        main_mod, "run", lambda coro: calls.setdefault("runner_calls", []).append(coro)
    )
    return calls


def run_cli(monkeypatch, *args: str) -> Any:
    monkeypatch.setattr(sys, "argv", ["prog", *args])
    main_mod.cli()


class TestCli:
    def test_tools_mode(self, monkeypatch, cli_spy):
        cli_spy["print_tools"].return_value = "tools-coro"
        run_cli(monkeypatch, "--tools")
        assert cli_spy["print_tools"].called
        assert cli_spy["install_playwright"].called

    def test_agents_mode(self, monkeypatch, cli_spy):
        run_cli(monkeypatch, "--agents")
        assert cli_spy["print_agents"].called

    def test_cli_agent_mode_default(self, monkeypatch, cli_spy):
        run_cli(monkeypatch)
        cli_spy["run_agent"].assert_called_once_with(dev=False)

    def test_cli_agent_dev_and_png(self, monkeypatch, cli_spy):
        run_cli(monkeypatch, "--dev")
        cli_spy["run_agent"].assert_called_once_with(dev=True)
        cli_spy["run_agent"].reset_mock()
        run_cli(monkeypatch, "--png")
        cli_spy["run_agent"].assert_called_once_with(generate_png=True)

    def test_telegram_mode_passes_flags(self, monkeypatch, cli_spy):
        run_cli(monkeypatch, "--telegram", "--dev", "--persist")
        cli_spy["run_telegram_bot"].assert_called_once_with(dev=True, persist=True)


class TestInstallPlaywright:
    def test_existing_install_only_creates_symlinks(
        self, monkeypatch, tmp_path, capsys
    ):
        home = tmp_path / "home"
        playwright = home / ".playwright"
        (playwright / "chrome-1209").mkdir(parents=True)
        (playwright / "chromium-1208").mkdir()
        monkeypatch.setenv("HOME", str(home))
        run = MagicMock()
        monkeypatch.setattr(main_mod.subprocess, "run", run)

        main_mod.install_playwright()

        run.assert_not_called()
        # A symlink aliases the missing 1208 chrome build to the 1209 one.
        assert (playwright / "chrome-1208").is_symlink()

    def test_missing_npm_exits(self, monkeypatch, tmp_path):
        home = tmp_path / "home"
        (home / ".playwright").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(main_mod.shutil, "which", lambda cmd: None)
        with pytest.raises(SystemExit) as excinfo:
            main_mod.install_playwright()
        assert excinfo.value.code == 1

    def test_installs_when_directory_empty(self, monkeypatch, tmp_path):
        home = tmp_path / "home"
        (home / ".playwright").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(main_mod.shutil, "which", lambda cmd: "/usr/bin/npm")
        run = MagicMock()
        monkeypatch.setattr(main_mod.subprocess, "run", run)

        main_mod.install_playwright()

        assert run.call_count == 3
        assert all(call.kwargs.get("check") is True for call in run.call_args_list)

    def test_subprocess_failure_exits(self, monkeypatch, tmp_path):
        home = tmp_path / "home"
        (home / ".playwright").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(main_mod.shutil, "which", lambda cmd: "/usr/bin/npm")
        monkeypatch.setattr(
            main_mod.subprocess,
            "run",
            MagicMock(side_effect=subprocess.CalledProcessError(1, ["npx"])),
        )
        with pytest.raises(SystemExit) as excinfo:
            main_mod.install_playwright()
        assert excinfo.value.code == 1

    def test_unexpected_error_exits(self, monkeypatch, tmp_path):
        home = tmp_path / "home"
        playwright = home / ".playwright"
        playwright.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(main_mod.shutil, "which", lambda cmd: "/usr/bin/npm")
        monkeypatch.setattr(main_mod.Path, "home", classmethod(lambda cls: _boom(home)))
        with pytest.raises(SystemExit) as excinfo:
            main_mod.install_playwright()
        assert excinfo.value.code == 1


def _boom(value: Path) -> Path:
    raise RuntimeError("unexpected")
