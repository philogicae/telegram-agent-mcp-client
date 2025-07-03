import argparse
from asyncio import run

from .src import run_agent, run_telegram_bot


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
    args = parser.parse_args()

    if args.telegram:
        run(run_telegram_bot(dev=args.dev))
    else:
        run(run_agent(dev=args.dev))


if __name__ == "__main__":
    cli()
