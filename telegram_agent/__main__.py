import argparse
from asyncio import run

from .src import GraphRAG, print_agents, print_tools, run_agent, run_telegram_bot


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

    if args.tools:
        run(print_tools())
    elif args.agents:
        run(print_agents())
    elif args.png:
        run(run_agent(generate_png=True))
    elif args.clear:
        run(GraphRAG().clear())
    elif args.telegram:
        run(run_telegram_bot(dev=args.dev))
    else:
        run(run_agent(dev=args.dev))


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        pass
