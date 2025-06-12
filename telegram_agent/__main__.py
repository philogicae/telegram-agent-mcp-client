from asyncio import run

from .src import run_agent


async def cli() -> None:
    # import argparse
    """parser = argparse.ArgumentParser(description="Run Telegram Agent MCP Client.")
    parser.add_argument(
        "--key",
        type=str,
        default="",
        help="Telegram Agent MCP Client key.",
    )
    args = parser.parse_args()"""

    await run_agent()


if __name__ == "__main__":
    run(cli())
