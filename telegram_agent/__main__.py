"""Main entry point for Telegram Agent MCP Client."""

from .patch_pydantic_v1 import _PYDANTIC_V1_ANCHOR

_PYDANTIC_V1_ANCHOR  # noqa: B018

import argparse
import shutil
import subprocess
import sys
from asyncio import run
from contextlib import suppress
from os import environ
from pathlib import Path
from traceback import print_exc

from .src import print_agents, print_tools, run_agent, run_telegram_bot

# Colors for output
RED = "\033[0;31m"
GREEN = "\033[0;32m"
ORANGE = "\033[1;33m"
NC = "\033[0m"  # No Color


def print_status(msg: str) -> None:
    """Print a status message in green."""
    print(f"{GREEN}{msg}{NC}")


def print_warning(msg: str) -> None:
    """Print a warning message in orange."""
    print(f"{ORANGE}{msg}{NC}")


def print_error(msg: str) -> None:
    """Print an error message in red."""
    print(f"{RED}{msg}{NC}")


def install_playwright() -> None:
    """Install Playwright dependencies."""
    try:
        playwright_location = Path.home() / ".playwright"
        # Check if installation is needed
        needs_install = True
        if playwright_location.exists() and playwright_location.is_dir():
            try:
                if any(playwright_location.iterdir()):
                    needs_install = False
            except OSError, PermissionError:
                pass

        if needs_install:
            print_status("Installing Playwright dependencies...")
            playwright_location.mkdir(parents=True, exist_ok=True)
            driver_env = {
                **environ.copy(),
                "PLAYWRIGHT_BROWSERS_PATH": playwright_location.as_posix(),
            }
            # Check for required commands
            if not shutil.which("npm"):
                print_error("npm not found. Please install Node.js and npm first.")
                sys.exit(1)

            playwright_dependencies = [
                (
                    "Playwright MCP dependencies",
                    [
                        "npx",
                        "-y",
                        "patchright@latest",
                        "install",
                        "--with-deps",
                        "chromium",
                    ],
                ),
                ("Playwright CLI", ["npm", "install", "-g", "@playwright/cli@latest"]),
                (
                    "Playwright CLI dependencies",
                    [
                        "npx",
                        "-y",
                        "patchright@latest",
                        "install",
                        "--with-deps",
                        "chrome",
                    ],
                ),
            ]
            for label, cmd in playwright_dependencies:
                print_status(f"- {label}...")
                subprocess.run(  # noqa: S603
                    cmd, env=driver_env, check=True, capture_output=True
                )
            print_status("Playwright dependencies installed.")

        # Symlinks for MCP - handle race conditions
        prefixes = ["chrome-", "chromium-", "chromium_headless_shell-"]
        # Always ensure version 1208 is available (hardcoded by fetcher-mcp)
        target_versions = {"1208"}
        versions = sorted(
            {
                d.name.rsplit("-", 1)[-1]
                for d in playwright_location.iterdir()
                if d.is_dir()
                and any(d.name.startswith(p) for p in prefixes)
                and d.name.rsplit("-", 1)[-1].isdigit()
            }
            | target_versions,
            key=int,
            reverse=True,
        )
        for prefix in prefixes:
            for v1 in versions:
                src = playwright_location / f"{prefix}{v1}"
                if src.is_dir():
                    for v2 in versions:
                        dst = playwright_location / f"{prefix}{v2}"
                        if dst == src:
                            continue
                        try:
                            if not dst.exists():
                                dst.symlink_to(src)
                        except FileExistsError:
                            # Race condition - symlink was created by another process
                            pass
                        except (OSError, PermissionError) as e:
                            print_warning(f"Could not create symlink {dst}: {e}")
                    break
    except subprocess.CalledProcessError as e:
        print_exc()
        print_error(f"Failed to install Playwright dependencies: {e}")
        sys.exit(1)
    except (OSError, PermissionError) as e:
        print_exc()
        print_error(f"Permission error during Playwright installation: {e}")
        sys.exit(1)
    except Exception as e:
        print_exc()
        print_error(f"Unexpected error installing Playwright dependencies: {e}")
        sys.exit(1)


def cli() -> None:
    """Parse CLI arguments and run the appropriate command."""
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
    args = parser.parse_args()

    install_playwright()

    if args.tools:
        run(print_tools())
    elif args.agents:
        run(print_agents())
    elif args.png:
        run(run_agent(generate_png=True))
    elif args.telegram:
        run(run_telegram_bot(dev=args.dev))
    else:
        run(run_agent(dev=args.dev))


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        cli()
