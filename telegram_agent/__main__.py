import argparse
import subprocess
from asyncio import run
from contextlib import suppress
from os import environ
from pathlib import Path

from playwright._impl._driver import compute_driver_executable, get_driver_env

from .src import GraphRAG, print_agents, print_tools, run_agent, run_telegram_bot


def install_playwright_drivers() -> None:
    """Install Playwright drivers and link headless shell versions."""
    with suppress(Exception):
        # 0. Skip if already installed
        playwright_location = Path.home() / ".playwright"
        if playwright_location.exists():
            return
        playwright_location.mkdir(parents=True)
        environ["PLAYWRIGHT_BROWSERS_PATH"] = playwright_location.as_posix()
        print("Installing Playwright drivers...")
        # 1. Build Command
        driver_executable, driver_cli = compute_driver_executable()
        playwright_command = [
            driver_executable,
            driver_cli,
            "install",
            "--with-deps",
            "chromium",
        ]
        # 2. Run Install
        subprocess.run(  # noqa: S603
            playwright_command,
            env=get_driver_env(),
            check=True,
            capture_output=True,  # Keeps stdout clean unless there's an error
        )
        # 3. Symlink
        src = playwright_location / "chromium_headless_shell-1208"
        dst = playwright_location / "chromium_headless_shell-1200"
        if src.exists():
            with suppress(OSError):
                if dst.is_symlink() or dst.exists():
                    dst.unlink()  # Equivalent to -f (force)
                dst.symlink_to(src)
        print("Playwright drivers installed.")
        return
    print("Failed to install Playwright drivers.")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run Telegram Agent MCP Client")
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Run as Telegram bot. Default: CLI",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in dev mode. Default: False",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="Display tools. Default: False",
    )
    parser.add_argument(
        "--agents",
        action="store_true",
        help="Display agents. Default: False",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Generate png. Default: False",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear graph. Default: False",
    )
    args = parser.parse_args()

    install_playwright_drivers()

    if args.tools:
        run(print_tools())
    elif args.agents:
        run(print_agents())
    elif args.png:
        run(run_agent(generate_png=True))
    elif args.clear:
        run(GraphRAG.init(clear=True))
    elif args.telegram:
        run(run_telegram_bot(dev=args.dev))
    else:
        run(run_agent(dev=args.dev))


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        pass
