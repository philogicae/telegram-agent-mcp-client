import argparse
from asyncio import run

from .src import run_agent, run_bot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Telegram Agent MCP Client")
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Run as Telegram bot. Default: CLI",
    )
    args = parser.parse_args()

    if args.telegram:
        run(run_bot())
    else:
        run(run_agent())
