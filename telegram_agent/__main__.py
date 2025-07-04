import argparse
from asyncio import run

from .src import run_agent, run_telegram_bot, run_tools


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
    args = parser.parse_args()

    if args.tools:
        run(run_tools())
    elif args.telegram:
        run(run_telegram_bot(dev=args.dev))
    else:
        run(run_agent(dev=args.dev))


if __name__ == "__main__":
    cli()
